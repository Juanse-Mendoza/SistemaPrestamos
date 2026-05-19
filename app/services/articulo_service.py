from __future__ import annotations

from app.database.connection import ejecutar_query, get_conn


def listar_articulos(solo_disponibles: bool = False) -> list[dict]:
    sql = "SELECT * FROM v_stock_disponible"
    if solo_disponibles:
        sql += " WHERE estado = 'disponible' AND stock_disponible > 0"
    return ejecutar_query(sql)


def obtener_articulo(articulo_id: int) -> dict | None:
    rows = ejecutar_query(
        "SELECT * FROM v_stock_disponible WHERE articulo_id = %s", (articulo_id,)
    )
    return rows[0] if rows else None


def listar_categorias() -> list[dict]:
    return ejecutar_query(
        "SELECT id, nombre FROM categorias WHERE activo = TRUE ORDER BY nombre"
    )


def registrar_articulo(nombre: str, descripcion: str | None, categoria_id: int | None,
                        stock_total: int, codigo_interno: str | None,
                        ubicacion: str | None, codigo_barras: str | None = None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_articulo(%s,%s,%s,%s,%s,%s,%s,NULL,NULL,NULL)",
                (nombre, descripcion, categoria_id, stock_total,
                 codigo_interno, ubicacion, codigo_barras),
            )
            row = cur.fetchone()
    if row and row["p_articulo_id"] > 0:
        return {"exito": True, "articulo_id": row["p_articulo_id"], "mensaje": row["p_mensaje"]}
    return {"exito": False, "articulo_id": None, "mensaje": row["p_mensaje"] if row else "Error."}


def actualizar_articulo(articulo_id: int, nombre: str,
                         descripcion: str | None, ubicacion: str | None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE articulos SET nombre=%s, descripcion=%s, ubicacion=%s WHERE id=%s AND activo=TRUE",
                (nombre, descripcion, ubicacion, articulo_id),
            )
            afectados = cur.rowcount
    return {"exito": bool(afectados), "mensaje": "Artículo actualizado." if afectados else "No encontrado."}


def actualizar_stock(articulo_id: int, nuevo_stock_total: int) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_actualizar_stock(%s,%s,NULL)", (articulo_id, nuevo_stock_total))
            row = cur.fetchone()
    msg = row["p_mensaje"] if row else "Error."
    return {"exito": "actualizado" in msg.lower(), "mensaje": msg}


def dar_baja_articulo(articulo_id: int, motivo: str) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_baja_articulo(%s,%s,NULL)", (articulo_id, motivo))
            row = cur.fetchone()
    msg = row["p_mensaje"] if row else "Error."
    return {"exito": "baja" in msg.lower() and "no se puede" not in msg.lower(), "mensaje": msg}


def buscar_por_codigo_barras(codigo: str) -> dict | None:
    rows = ejecutar_query(
        "SELECT * FROM v_stock_disponible WHERE codigo_barras = %s", (codigo,)
    )
    return rows[0] if rows else None
