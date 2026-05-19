from __future__ import annotations

import secrets
from datetime import datetime

from app.database.connection import ejecutar_query, get_conn


def registrar_prestamo(usuario_id: int, articulo_id: int,
                        fecha_devolucion: datetime, admin_id: int | None,
                        observaciones: str | None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_prestamo(%s,%s,%s,%s,%s,NULL,NULL,NULL)",
                (usuario_id, articulo_id, fecha_devolucion, admin_id, observaciones),
            )
            row = cur.fetchone()
    if not row or not row["p_prestamo_id"] or row["p_prestamo_id"] <= 0:
        return {"exito": False, "mensaje": row["p_mensaje"] if row else "Error."}

    prestamo_id     = row["p_prestamo_id"]
    codigo_prestamo = row["p_codigo_prestamo"]

    # Si el cliente se autosolicita (sin admin), auto-aceptamos el préstamo
    if admin_id is None:
        aceptar_prestamo(prestamo_id, usuario_id)
        return {"exito": True, "prestamo_id": prestamo_id,
                "codigo_prestamo": codigo_prestamo,
                "mensaje": f"Préstamo activo. Código: {codigo_prestamo}"}

    return {"exito": True, "prestamo_id": prestamo_id,
            "codigo_prestamo": codigo_prestamo, "mensaje": row["p_mensaje"]}


def registrar_devolucion(prestamo_id: int, estado_articulo: str,
                          admin_id: int | None, observaciones: str | None,
                          fecha_devolucion: datetime | None = None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_devolucion(%s,%s::estado_articulo,%s,%s,%s,NULL,NULL)",
                (prestamo_id, estado_articulo, admin_id, observaciones, fecha_devolucion),
            )
            row = cur.fetchone()
    if row and row["p_devolucion_id"] and row["p_devolucion_id"] > 0:
        return {"exito": True, "mensaje": row["p_mensaje"]}
    return {"exito": False, "mensaje": row["p_mensaje"] if row else "Error."}


def listar_prestamos_activos() -> list[dict]:
    return ejecutar_query("SELECT * FROM v_prestamos_activos")


def listar_prestamos_en_curso() -> list[dict]:
    """Préstamos sin devolver: 'activo' (a tiempo) y 'vencido' (fecha pasada)."""
    return ejecutar_query(
        """
        SELECT
            p.id                              AS prestamo_id,
            p.codigo_prestamo,
            p.codigo_solicitud,
            u.nombre || ' ' || u.apellido     AS usuario_nombre,
            u.correo                          AS usuario_correo,
            u.numero_documento,
            a.nombre                          AS articulo,
            a.codigo_interno,
            p.fecha_prestamo,
            p.fecha_devolucion_esperada,
            p.estado                          AS estado_prestamo,
            CASE
                WHEN p.fecha_devolucion_esperada < NOW() THEN 'VENCIDO'
                ELSE 'A TIEMPO'
            END                               AS estado_tiempo,
            GREATEST(
                EXTRACT(DAY FROM NOW() - p.fecha_devolucion_esperada)::INTEGER, 0
            )                                 AS dias_retraso,
            p.observaciones
        FROM prestamos p
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE p.estado IN ('activo', 'vencido')
        ORDER BY COALESCE(p.codigo_solicitud, p.codigo_prestamo), p.fecha_devolucion_esperada ASC
        """
    )


def historial_completo(fecha_inicio: datetime | None = None,
                        fecha_fin: datetime | None = None) -> list[dict]:
    if fecha_inicio and fecha_fin:
        return ejecutar_query(
            "SELECT * FROM v_historial_prestamos WHERE fecha_prestamo BETWEEN %s AND %s",
            (fecha_inicio, fecha_fin),
        )
    return ejecutar_query("SELECT * FROM v_historial_prestamos")


def historial_usuario(usuario_id: int) -> list[dict]:
    return ejecutar_query("SELECT * FROM fn_historial_usuario(%s)", (usuario_id,))


def metricas_reporte() -> dict:
    rows = ejecutar_query("SELECT * FROM fn_reporte_general()")
    return rows[0] if rows else {}


def articulos_mas_prestados() -> list[dict]:
    return ejecutar_query("SELECT * FROM v_articulos_mas_prestados LIMIT 10")


def actualizar_prestamos_vencidos() -> int:
    rows = ejecutar_query("SELECT fn_marcar_prestamos_vencidos() AS n")
    return rows[0]["n"] if rows else 0


def listar_usuarios() -> list[dict]:
    return ejecutar_query("SELECT * FROM v_usuarios")


# ── Sistema de multas (COP por hora de retraso) ──────────────────────────────

TASA_MULTA_HORA_COP_DEFAULT = 1000  # tarifa global si el artículo no tiene una propia


def calcular_multa_cop(fecha_dev_esperada: datetime,
                        fecha_dev_real: datetime | None = None,
                        tasa_hora: int | float | None = None) -> dict:
    """Calcula la multa en COP usando la tarifa específica del artículo (o default).

    - Si el préstamo está activo/vencido (fecha_dev_real = None), usa NOW().
    - Si fue devuelto, congela el monto a la fecha real.
    - Retorna {horas, monto, vencido, tasa_hora}.
    """
    if not fecha_dev_esperada:
        return {"horas": 0, "monto": 0, "vencido": False, "tasa_hora": 0}
    referencia = fecha_dev_real if fecha_dev_real else datetime.now()
    if referencia <= fecha_dev_esperada:
        return {"horas": 0, "monto": 0, "vencido": False, "tasa_hora": 0}
    delta = referencia - fecha_dev_esperada
    horas = int(delta.total_seconds() // 3600)
    if delta.total_seconds() % 3600 > 0:
        horas += 1  # redondeo hacia arriba
    tasa = float(tasa_hora) if tasa_hora is not None else float(TASA_MULTA_HORA_COP_DEFAULT)
    monto = horas * tasa
    return {"horas": horas, "monto": monto, "vencido": True, "tasa_hora": tasa}


def formatear_cop(monto: int | float | None) -> str:
    """Formatea un monto en pesos colombianos: '$ 25.000 COP'."""
    if monto is None:
        return "$ 0 COP"
    return f"$ {int(monto):,} COP".replace(",", ".")


def _enriquecer_multa(r: dict) -> dict | None:
    """Calcula multa, pagos y saldo para una fila de préstamo. Retorna None si saldo<=0."""
    multa = calcular_multa_cop(
        r["fecha_devolucion_esperada"],
        r["fecha_devolucion_real"],
        r.get("multa_por_hora_cop"),
    )
    if multa["monto"] <= 0:
        return None
    # Sumar pagos de la tabla pagos_multa
    pagos = ejecutar_query(
        "SELECT COALESCE(SUM(monto), 0) AS total FROM pagos_multa WHERE prestamo_id = %s",
        (r["prestamo_id"],),
    )
    pagado = float(pagos[0]["total"]) if pagos else 0.0
    saldo  = max(multa["monto"] - pagado, 0)
    if saldo <= 0:
        return None  # ya pagada totalmente
    r["multa_horas"]            = multa["horas"]
    r["multa_monto"]            = multa["monto"]
    r["multa_pagado"]           = pagado
    r["multa_saldo"]            = saldo
    r["multa_tasa_hora"]        = multa["tasa_hora"]
    r["multa_monto_formato"]    = formatear_cop(multa["monto"])
    r["multa_pagado_formato"]   = formatear_cop(pagado)
    r["multa_saldo_formato"]    = formatear_cop(saldo)
    r["multa_tasa_hora_formato"] = formatear_cop(multa["tasa_hora"])
    r["aun_activo"]             = r["fecha_devolucion_real"] is None
    return r


def listar_multas_pendientes_usuario(usuario_id: int) -> list[dict]:
    rows = ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               p.fecha_prestamo, p.fecha_devolucion_esperada,
               p.fecha_devolucion_real, p.estado,
               a.nombre AS articulo,
               a.multa_por_hora_cop
        FROM prestamos p
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE p.usuario_id = %s
          AND p.fecha_devolucion_esperada < COALESCE(p.fecha_devolucion_real, NOW())
          AND p.estado IN ('activo', 'vencido', 'devuelto')
        ORDER BY p.fecha_devolucion_esperada DESC
        """,
        (usuario_id,),
    )
    return [r for r in (_enriquecer_multa(r) for r in rows) if r is not None]


def listar_multas_pendientes_admin() -> list[dict]:
    rows = ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               p.fecha_prestamo, p.fecha_devolucion_esperada,
               p.fecha_devolucion_real, p.estado,
               u.id AS usuario_id,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo, u.numero_documento,
               a.nombre AS articulo,
               a.multa_por_hora_cop
        FROM prestamos p
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE p.fecha_devolucion_esperada < COALESCE(p.fecha_devolucion_real, NOW())
          AND p.estado IN ('activo', 'vencido', 'devuelto')
        ORDER BY p.fecha_devolucion_esperada ASC
        """,
    )
    return [r for r in (_enriquecer_multa(r) for r in rows) if r is not None]


def listar_pagos_multa(prestamo_id: int) -> list[dict]:
    """Historial de pagos hechos sobre una multa."""
    return ejecutar_query(
        """
        SELECT pm.id, pm.monto, pm.fecha_pago, pm.observaciones,
               u.nombre || ' ' || u.apellido AS admin_recibe
        FROM pagos_multa pm
        LEFT JOIN usuarios u ON u.id = pm.admin_recibe_id
        WHERE pm.prestamo_id = %s
        ORDER BY pm.fecha_pago DESC
        """,
        (prestamo_id,),
    )


def registrar_pago_multa(prestamo_id: int, admin_id: int,
                          monto: float, observaciones: str | None = None) -> dict:
    """Registra un pago (parcial o total) de la multa.

    Si el monto supera el saldo restante, devuelve error.
    Si tras el pago queda saldo, la multa sigue apareciendo en pendientes.
    Si saldo llega a 0, marca el préstamo como multa_pagada=TRUE.
    """
    if monto is None or monto <= 0:
        return {"exito": False, "mensaje": "El monto debe ser mayor a 0."}

    rows = ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.fecha_devolucion_esperada, p.fecha_devolucion_real,
               a.multa_por_hora_cop
        FROM prestamos p
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE p.id = %s
        """,
        (prestamo_id,),
    )
    if not rows:
        return {"exito": False, "mensaje": "Préstamo no encontrado."}

    r = rows[0]
    multa = calcular_multa_cop(
        r["fecha_devolucion_esperada"], r["fecha_devolucion_real"],
        r.get("multa_por_hora_cop"),
    )
    if multa["monto"] <= 0:
        return {"exito": False, "mensaje": "Este préstamo no tiene multa."}

    pagos_prev = ejecutar_query(
        "SELECT COALESCE(SUM(monto), 0) AS total FROM pagos_multa WHERE prestamo_id = %s",
        (prestamo_id,),
    )
    pagado_prev = float(pagos_prev[0]["total"]) if pagos_prev else 0.0
    saldo = multa["monto"] - pagado_prev
    if saldo <= 0:
        return {"exito": False, "mensaje": "Esta multa ya está totalmente pagada."}

    if monto > saldo:
        return {"exito": False,
                "mensaje": f"El monto ({formatear_cop(monto)}) excede el saldo pendiente ({formatear_cop(saldo)})."}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO pagos_multa (prestamo_id, monto, admin_recibe_id, observaciones)
                   VALUES (%s, %s, %s, %s)""",
                (prestamo_id, monto, admin_id, observaciones),
            )
            nuevo_saldo = saldo - monto
            if nuevo_saldo <= 0:
                cur.execute(
                    """UPDATE prestamos
                       SET multa_pagada = TRUE,
                           multa_monto_pagado = %s,
                           multa_fecha_pago = NOW(),
                           multa_admin_recibe_id = %s
                       WHERE id = %s""",
                    (pagado_prev + monto, admin_id, prestamo_id),
                )
    if nuevo_saldo <= 0:
        return {"exito": True,
                "mensaje": f"Pago de {formatear_cop(monto)} registrado. Multa totalmente saldada."}
    return {"exito": True,
            "mensaje": f"Abono de {formatear_cop(monto)} registrado. Saldo pendiente: {formatear_cop(nuevo_saldo)}."}


def registrar_prestamo_multiple(usuario_id: int, admin_id: int | None,
                                  items: list[dict], observaciones: str | None) -> dict:
    """Crea hasta 2 préstamos ligados por un mismo codigo_solicitud.

    items: lista de {'articulo_id': int, 'fecha_devolucion': datetime}
    Si solo hay 1, no se asigna codigo_solicitud.
    Devuelve los resultados de cada préstamo creado.
    """
    if not items:
        return {"exito": False, "mensaje": "Debe especificar al menos un artículo."}
    if len(items) > 2:
        return {"exito": False, "mensaje": "Máximo 2 artículos por solicitud."}

    # Validar que no se repita el mismo artículo
    if len(items) == 2 and items[0]["articulo_id"] == items[1]["articulo_id"]:
        return {"exito": False,
                "mensaje": "No puede registrar dos veces el mismo artículo. Aumente el stock o use otro."}

    codigo_solicitud = None
    if len(items) > 1:
        codigo_solicitud = f"SOL-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

    resultados = []
    for it in items:
        res = registrar_prestamo(
            usuario_id, it["articulo_id"], it["fecha_devolucion"],
            admin_id, observaciones,
        )
        if not res["exito"]:
            # Si uno falla, revertir los anteriores creando un mensaje claro
            return {"exito": False,
                    "mensaje": f"Falló el artículo {it['articulo_id']}: {res['mensaje']}. "
                               f"Préstamos creados antes: {[r.get('codigo_prestamo') for r in resultados]}",
                    "resultados": resultados}
        resultados.append(res)

    # Si hay codigo_solicitud, asignárselo a los préstamos creados
    if codigo_solicitud and resultados:
        ids = [r["prestamo_id"] for r in resultados]
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE prestamos SET codigo_solicitud = %s WHERE id = ANY(%s)",
                    (codigo_solicitud, ids),
                )

    return {
        "exito": True,
        "codigo_solicitud": codigo_solicitud,
        "resultados": resultados,
        "mensaje": (
            f"Solicitud {codigo_solicitud} creada con {len(resultados)} artículos."
            if codigo_solicitud else resultados[0]["mensaje"]
        ),
    }


# ── Flujo pendiente → aceptar / rechazar ──────────────────────────────────────

def aceptar_prestamo(prestamo_id: int, usuario_id: int,
                      motivo: str | None = None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_aceptar_prestamo(%s,%s,%s,NULL)",
                (prestamo_id, usuario_id, motivo),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": "exitosamente" in mensaje.lower(), "mensaje": mensaje}


def rechazar_prestamo(prestamo_id: int, usuario_id: int,
                       motivo: str | None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_rechazar_prestamo(%s,%s,%s,NULL)",
                (prestamo_id, usuario_id, motivo),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    exito = mensaje.startswith("Préstamo rechazado")
    return {"exito": exito, "mensaje": mensaje}


def listar_pendientes_usuario(usuario_id: int) -> list[dict]:
    return ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               a.nombre AS articulo, a.descripcion AS descripcion_articulo,
               c.nombre AS categoria, a.ubicacion,
               p.fecha_prestamo, p.fecha_devolucion_esperada, p.observaciones
        FROM prestamos p
        INNER JOIN articulos a ON a.id = p.articulo_id
        LEFT  JOIN categorias c ON c.id = a.categoria_id
        WHERE p.usuario_id = %s AND p.estado = 'pendiente'
        ORDER BY p.fecha_prestamo DESC
        """,
        (usuario_id,),
    )


def listar_pendientes_todos() -> list[dict]:
    return ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo, u.numero_documento,
               a.nombre AS articulo,
               p.fecha_prestamo, p.fecha_devolucion_esperada
        FROM prestamos p
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE p.estado = 'pendiente'
        ORDER BY p.fecha_prestamo DESC
        """,
    )


# ── Confirmación de devolución por el estudiante ──────────────────────────────

def listar_devoluciones_pendientes_usuario(usuario_id: int) -> list[dict]:
    """Devoluciones que el estudiante aún no ha confirmado ni rechazado."""
    return ejecutar_query(
        """
        SELECT d.id              AS devolucion_id,
               p.codigo_prestamo,
               a.nombre           AS articulo,
               d.fecha_devolucion,
               d.estado_articulo_recibido,
               d.observaciones,
               u.nombre || ' ' || u.apellido AS admin_recibe,
               p.fecha_devolucion_esperada
        FROM devoluciones d
        INNER JOIN prestamos p  ON p.id = d.prestamo_id
        INNER JOIN articulos a  ON a.id = p.articulo_id
        LEFT  JOIN usuarios u   ON u.id = d.administrador_recibe_id
        WHERE p.usuario_id = %s
          AND d.confirmada_estudiante IS NULL
        ORDER BY d.fecha_devolucion DESC
        """,
        (usuario_id,),
    )


def listar_devoluciones_disputa() -> list[dict]:
    """Devoluciones rechazadas por el estudiante (admin debe gestionar)."""
    return ejecutar_query(
        """
        SELECT d.id              AS devolucion_id,
               p.codigo_prestamo,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo                       AS usuario_correo,
               a.nombre           AS articulo,
               d.fecha_devolucion,
               d.estado_articulo_recibido,
               d.motivo_rechazo,
               d.fecha_confirmacion
        FROM devoluciones d
        INNER JOIN prestamos p  ON p.id = d.prestamo_id
        INNER JOIN usuarios u   ON u.id = p.usuario_id
        INNER JOIN articulos a  ON a.id = p.articulo_id
        WHERE d.confirmada_estudiante = FALSE
        ORDER BY d.fecha_confirmacion DESC
        """,
    )


def confirmar_devolucion(devolucion_id: int, usuario_id: int,
                          motivo: str | None = None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_confirmar_devolucion(%s,%s,%s,NULL)",
                (devolucion_id, usuario_id, motivo),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": mensaje.startswith("Devolución confirmada"), "mensaje": mensaje}


def rechazar_devolucion(devolucion_id: int, usuario_id: int, motivo: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_rechazar_devolucion(%s,%s,%s,NULL)",
                (devolucion_id, usuario_id, motivo),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": mensaje.startswith("Rechazo registrado"), "mensaje": mensaje}


def contar_pendientes_usuario(usuario_id: int) -> int:
    rows = ejecutar_query(
        "SELECT COUNT(*) AS n FROM prestamos WHERE usuario_id = %s AND estado = 'pendiente'",
        (usuario_id,),
    )
    return int(rows[0]["n"]) if rows else 0


def contar_solicitudes_cliente(usuario_id: int) -> dict:
    """Conteos para el badge del menú del estudiante."""
    rows = ejecutar_query(
        """
        SELECT
          (SELECT COUNT(*) FROM prestamos
            WHERE usuario_id = %s AND estado = 'pendiente') AS n_prestamos,
          (SELECT COUNT(*) FROM devoluciones d
            INNER JOIN prestamos p ON p.id = d.prestamo_id
            WHERE p.usuario_id = %s AND d.confirmada_estudiante IS NULL) AS n_devoluciones
        """,
        (usuario_id, usuario_id),
    )
    n_p = int(rows[0]["n_prestamos"]) if rows else 0
    n_d = int(rows[0]["n_devoluciones"]) if rows else 0
    return {"prestamos": n_p, "devoluciones": n_d, "total": n_p + n_d}


def obtener_pendiente_detalle(prestamo_id: int) -> dict | None:
    rows = ejecutar_query(
        """
        SELECT p.id AS prestamo_id, p.codigo_prestamo, p.observaciones,
               p.fecha_prestamo, p.fecha_devolucion_esperada,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo, u.numero_documento,
               a.nombre AS articulo, a.codigo_interno, a.ubicacion,
               c.nombre AS categoria
        FROM prestamos p
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        LEFT  JOIN categorias c ON c.id = a.categoria_id
        WHERE p.id = %s AND p.estado = 'pendiente'
        """,
        (prestamo_id,),
    )
    return rows[0] if rows else None


def obtener_disputa_detalle(devolucion_id: int) -> dict | None:
    rows = ejecutar_query(
        """
        SELECT d.id AS devolucion_id, d.estado_articulo_recibido,
               d.fecha_devolucion, d.observaciones, d.motivo_rechazo,
               d.fecha_confirmacion,
               p.codigo_prestamo, p.fecha_prestamo, p.fecha_devolucion_esperada,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo,
               a.nombre AS articulo,
               admin_rec.nombre || ' ' || admin_rec.apellido AS admin_recibio
        FROM devoluciones d
        INNER JOIN prestamos p ON p.id = d.prestamo_id
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        LEFT  JOIN usuarios admin_rec ON admin_rec.id = d.administrador_recibe_id
        WHERE d.id = %s AND d.confirmada_estudiante = FALSE
        """,
        (devolucion_id,),
    )
    return rows[0] if rows else None


def obtener_disputa_cualquier_estado(devolucion_id: int) -> dict | None:
    """Detalle de una disputa, sin importar si está activa, cerrada o corregida."""
    rows = ejecutar_query(
        """
        SELECT d.id AS devolucion_id, d.estado_articulo_recibido,
               d.fecha_devolucion, d.observaciones, d.motivo_rechazo,
               d.fecha_confirmacion, d.confirmada_estudiante,
               p.codigo_prestamo, p.fecha_prestamo, p.fecha_devolucion_esperada,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo,
               a.nombre AS articulo,
               admin_rec.nombre || ' ' || admin_rec.apellido AS admin_recibio
        FROM devoluciones d
        INNER JOIN prestamos p ON p.id = d.prestamo_id
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        LEFT  JOIN usuarios admin_rec ON admin_rec.id = d.administrador_recibe_id
        WHERE d.id = %s AND d.motivo_rechazo IS NOT NULL
        """,
        (devolucion_id,),
    )
    return rows[0] if rows else None


def cancelar_prestamo_pendiente(prestamo_id: int, admin_id: int, motivo: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_cancelar_prestamo_pendiente(%s,%s,%s,NULL)",
                (prestamo_id, admin_id, motivo),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": mensaje.startswith("Préstamo cancelado"), "mensaje": mensaje}


def corregir_devolucion(devolucion_id: int, admin_id: int,
                         nuevo_estado: str, nuevas_obs: str | None,
                         nota_admin: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_corregir_devolucion(%s,%s,%s::estado_articulo,%s,%s,NULL)",
                (devolucion_id, admin_id, nuevo_estado, nuevas_obs, nota_admin),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": mensaje.startswith("Devolución corregida"), "mensaje": mensaje}


def historial_disputas(estado: str | None = None,
                        desde: datetime | None = None,
                        hasta: datetime | None = None) -> list[dict]:
    """Todas las devoluciones que en algún momento fueron disputadas.

    estado: 'activa' | 'cerrada' | 'corregida' | None (todas)
    """
    sql = """
        SELECT d.id AS devolucion_id,
               p.codigo_prestamo,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo                       AS usuario_correo,
               a.nombre                       AS articulo,
               d.estado_articulo_recibido,
               d.fecha_devolucion,
               d.fecha_confirmacion,
               d.motivo_rechazo,
               d.observaciones,
               d.confirmada_estudiante,
               CASE
                  WHEN d.confirmada_estudiante = FALSE THEN 'activa'
                  WHEN d.confirmada_estudiante = TRUE  THEN 'cerrada'
                  WHEN d.confirmada_estudiante IS NULL THEN 'corregida'
               END AS estado_disputa
        FROM devoluciones d
        INNER JOIN prestamos p ON p.id = d.prestamo_id
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        INNER JOIN articulos a ON a.id = p.articulo_id
        WHERE d.motivo_rechazo IS NOT NULL
    """
    params: list = []
    if estado in ("activa", "cerrada", "corregida"):
        sql += " AND CASE WHEN d.confirmada_estudiante = FALSE THEN 'activa' " \
               " WHEN d.confirmada_estudiante = TRUE THEN 'cerrada' " \
               " ELSE 'corregida' END = %s"
        params.append(estado)
    if desde:
        sql += " AND d.fecha_devolucion >= %s"
        params.append(desde)
    if hasta:
        sql += " AND d.fecha_devolucion <= %s"
        params.append(hasta)
    sql += " ORDER BY COALESCE(d.fecha_confirmacion, d.fecha_devolucion) DESC"
    return ejecutar_query(sql, tuple(params) if params else None)


def cerrar_disputa(devolucion_id: int, admin_id: int, nota: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_cerrar_disputa(%s,%s,%s,NULL)",
                (devolucion_id, admin_id, nota),
            )
            row = cur.fetchone()
    mensaje = row["p_mensaje"] if row else "Error."
    return {"exito": mensaje.startswith("Disputa cerrada"), "mensaje": mensaje}


def contar_solicitudes_admin() -> dict:
    """Conteos para el badge del menú del admin."""
    rows = ejecutar_query(
        """
        SELECT
          (SELECT COUNT(*) FROM prestamos WHERE estado = 'pendiente') AS n_prestamos,
          (SELECT COUNT(*) FROM devoluciones WHERE confirmada_estudiante = FALSE) AS n_disputas
        """,
    )
    n_p = int(rows[0]["n_prestamos"]) if rows else 0
    n_d = int(rows[0]["n_disputas"]) if rows else 0
    return {"prestamos": n_p, "disputas": n_d, "total": n_p + n_d}
