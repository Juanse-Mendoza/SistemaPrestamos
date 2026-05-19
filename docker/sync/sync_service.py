"""
Servicio de sincronización PostgreSQL → SQL Server.
Se ejecuta dentro del contenedor 'prestamos_sync' de Docker.

Cada SYNC_INTERVAL_SECONDS segundos copia el estado actual de PostgreSQL
hacia la base de datos réplica en SQL Server.

La sincronización es una réplica completa por tabla (truncate + insert),
apropiada para un volumen de datos académico. Para producción real
se recomendaría replicación lógica con pglogical o Debezium.

Captura de pantalla sugerida: logs del contenedor sync mostrando
las tablas sincronizadas y el resumen de registros.
"""

import json
import logging
import os
import time
from datetime import datetime

import psycopg2
import psycopg2.extras
import pymssql

# ─── Configuración ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SYNC] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sync")

PG_CONFIG = {
    "host":     os.environ.get("PG_HOST", "postgres"),
    "port":     int(os.environ.get("PG_PORT", 5432)),
    "dbname":   os.environ.get("PG_DB", "prestamos_umb"),
    "user":     os.environ.get("PG_USER", "app_prestamos"),
    "password": os.environ.get("PG_PASSWORD", ""),
}

SS_CONFIG = {
    "server":   os.environ.get("SS_HOST", "sqlserver"),
    "port":     int(os.environ.get("SS_PORT", 1433)),
    "database": os.environ.get("SS_DB", "prestamos_umb_copia"),
    "user":     os.environ.get("SS_USER", "sa"),
    "password": os.environ.get("SS_PASSWORD", ""),
}

SYNC_INTERVAL = int(os.environ.get("SYNC_INTERVAL_SECONDS", 300))

# Orden de sincronización (respeta FK: primero tablas padre)
TABLAS_SYNC = [
    "roles",
    "usuarios",
    "categorias",
    "articulos",
    "prestamos",
    "devoluciones",
    "historial_operaciones",
]

# Columnas de cada tabla (deben coincidir con la BD)
COLUMNAS = {
    "roles": ["id", "nombre", "descripcion", "fecha_creacion"],
    "usuarios": ["id", "nombre", "apellido", "correo", "password_hash", "rol_id",
                 "codigo_barras", "numero_documento", "activo",
                 "fecha_creacion", "fecha_actualizacion"],
    "categorias": ["id", "nombre", "descripcion", "activo", "fecha_creacion"],
    "articulos": ["id", "nombre", "descripcion", "categoria_id", "estado",
                  "stock_total", "stock_disponible", "codigo_barras",
                  "codigo_interno", "ubicacion", "activo",
                  "fecha_registro", "fecha_actualizacion"],
    "prestamos": ["id", "usuario_id", "articulo_id", "administrador_autoriza_id",
                  "estado", "fecha_prestamo", "fecha_devolucion_esperada",
                  "fecha_devolucion_real", "observaciones", "codigo_prestamo"],
    "devoluciones": ["id", "prestamo_id", "administrador_recibe_id",
                     "estado_articulo_recibido", "fecha_devolucion", "observaciones"],
    "historial_operaciones": ["id", "tabla_afectada", "operacion", "registro_id",
                              "usuario_db", "datos_anteriores", "datos_nuevos",
                              "ip_cliente", "fecha"],
}


# ─── Conexiones ────────────────────────────────────────────────────────────────

def conectar_postgres():
    return psycopg2.connect(**PG_CONFIG)


def conectar_sqlserver():
    return pymssql.connect(
        server=SS_CONFIG["server"],
        port=SS_CONFIG["port"],
        database=SS_CONFIG["database"],
        user=SS_CONFIG["user"],
        password=SS_CONFIG["password"],
        charset="UTF8",
    )


# ─── Lógica de sincronización ──────────────────────────────────────────────────

def sync_tabla(pg_cur, ss_conn, tabla: str) -> int:
    """
    Sincroniza una tabla de PostgreSQL hacia SQL Server.
    Estrategia: DELETE + INSERT (réplica completa de la tabla).
    Retorna el número de registros sincronizados.
    """
    cols = COLUMNAS[tabla]
    cols_str = ", ".join(cols)

    # 1. Leer desde PostgreSQL
    pg_cur.execute(f"SELECT {cols_str} FROM {tabla} ORDER BY id")
    filas = pg_cur.fetchall()

    ss_cur = ss_conn.cursor()

    # 2. Deshabilitar constraints FK temporalmente en SQL Server
    ss_cur.execute(f"ALTER TABLE {tabla} NOCHECK CONSTRAINT ALL")

    # 3. Limpiar tabla destino
    ss_cur.execute(f"DELETE FROM {tabla}")

    # 4. Habilitar inserción en columnas IDENTITY
    ss_cur.execute(f"SET IDENTITY_INSERT {tabla} ON")

    # 5. Insertar registros
    if filas:
        placeholders = ", ".join(["%s"] * len(cols))
        insert_sql = f"INSERT INTO {tabla} ({cols_str}) VALUES ({placeholders})"

        for fila in filas:
            valores = []
            for i, col in enumerate(cols):
                val = fila[i]
                # Convertir tipos especiales
                if isinstance(val, dict):
                    val = json.dumps(val, ensure_ascii=False, default=str)
                elif hasattr(val, 'isoformat'):  # datetime
                    val = val  # pymssql acepta datetime directamente
                elif isinstance(val, memoryview):
                    val = bytes(val)
                valores.append(val)
            ss_cur.execute(insert_sql, tuple(valores))

    # 6. Deshabilitar IDENTITY_INSERT y re-habilitar constraints
    ss_cur.execute(f"SET IDENTITY_INSERT {tabla} OFF")
    ss_cur.execute(f"ALTER TABLE {tabla} WITH CHECK CHECK CONSTRAINT ALL")

    return len(filas)


def registrar_sync_log(ss_conn, inicio: datetime, fin: datetime,
                        total: int, estado: str, mensaje: str = None):
    """Registra el resultado de la sincronización en la tabla sync_log de SQL Server."""
    try:
        cur = ss_conn.cursor()
        cur.execute(
            """INSERT INTO sync_log (fecha_inicio, fecha_fin, registros_sync, estado, mensaje)
               VALUES (%s, %s, %s, %s, %s)""",
            (inicio, fin, total, estado, mensaje),
        )
        ss_conn.commit()
    except Exception as e:
        log.warning(f"No se pudo registrar en sync_log: {e}")


def ejecutar_sync():
    """Ejecuta un ciclo completo de sincronización PostgreSQL → SQL Server."""
    inicio = datetime.now()
    total_registros = 0
    log.info("─" * 50)
    log.info("Iniciando sincronización...")

    pg_conn = None
    ss_conn = None

    try:
        pg_conn = conectar_postgres()
        pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        ss_conn = conectar_sqlserver()

        for tabla in TABLAS_SYNC:
            try:
                n = sync_tabla(pg_cur, ss_conn, tabla)
                ss_conn.commit()
                total_registros += n
                log.info(f"  ✓ {tabla:<30} {n:>5} registros")
            except Exception as e:
                ss_conn.rollback()
                log.error(f"  ✗ Error sincronizando {tabla}: {e}")

        fin = datetime.now()
        duracion = (fin - inicio).total_seconds()
        log.info(f"Sincronización completada: {total_registros} registros en {duracion:.1f}s")
        registrar_sync_log(ss_conn, inicio, fin, total_registros, "completado")

    except psycopg2.OperationalError as e:
        log.error(f"Error conectando a PostgreSQL: {e}")
        if ss_conn:
            registrar_sync_log(ss_conn, inicio, datetime.now(), 0, "error", str(e))
    except pymssql.OperationalError as e:
        log.error(f"Error conectando a SQL Server: {e}")
    except Exception as e:
        log.error(f"Error inesperado: {e}")
        if ss_conn:
            registrar_sync_log(ss_conn, inicio, datetime.now(), 0, "error", str(e))
    finally:
        if pg_conn:
            pg_conn.close()
        if ss_conn:
            ss_conn.close()


# ─── Punto de entrada ──────────────────────────────────────────────────────────

def main():
    log.info("=" * 50)
    log.info("  Servicio de sincronización PG → SQL Server")
    log.info(f"  Intervalo: cada {SYNC_INTERVAL}s ({SYNC_INTERVAL // 60} min)")
    log.info(f"  Origen:    {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
    log.info(f"  Destino:   {SS_CONFIG['server']}:{SS_CONFIG['port']}/{SS_CONFIG['database']}")
    log.info("=" * 50)

    # Esperar que ambas BDs estén disponibles antes del primer sync
    log.info("Esperando disponibilidad de las bases de datos...")
    time.sleep(30)

    while True:
        try:
            ejecutar_sync()
        except Exception as e:
            log.error(f"Fallo en ciclo de sync: {e}")

        log.info(f"Próxima sincronización en {SYNC_INTERVAL}s...")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
