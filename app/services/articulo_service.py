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
                        ubicacion: str | None, codigo_barras: str | None = None,
                        tiempo_maximo_minutos: int | None = None,
                        multa_por_hora_cop: float | None = None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_articulo(%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL)",
                (nombre, descripcion, categoria_id, stock_total,
                 codigo_interno, ubicacion, codigo_barras, tiempo_maximo_minutos),
            )
            row = cur.fetchone()
            if row and row["p_articulo_id"] > 0 and multa_por_hora_cop is not None:
                cur.execute(
                    "UPDATE articulos SET multa_por_hora_cop = %s WHERE id = %s",
                    (multa_por_hora_cop, row["p_articulo_id"]),
                )
    if row and row["p_articulo_id"] > 0:
        return {"exito": True, "articulo_id": row["p_articulo_id"], "mensaje": row["p_mensaje"]}
    return {"exito": False, "articulo_id": None, "mensaje": row["p_mensaje"] if row else "Error."}


def actualizar_articulo(articulo_id: int, nombre: str,
                         descripcion: str | None, ubicacion: str | None,
                         codigo_barras: str | None = None,
                         tiempo_maximo_minutos: int | None = None,
                         estado: str | None = None,
                         multa_por_hora_cop: float | None = None,
                         actualizar_multa: bool = False) -> dict:
    # Validar que el código de barras no esté en otro artículo
    if codigo_barras:
        rows = ejecutar_query(
            "SELECT id FROM articulos WHERE codigo_barras = %s AND id != %s",
            (codigo_barras, articulo_id),
        )
        if rows:
            return {"exito": False,
                    "mensaje": f"El código de barras '{codigo_barras}' ya está usado por otro artículo."}
    if tiempo_maximo_minutos is not None and tiempo_maximo_minutos <= 0:
        return {"exito": False,
                "mensaje": "El tiempo máximo de préstamo debe ser mayor a 0."}

    # Validar estado (solo permitir disponible o mantenimiento desde edición)
    if estado and estado not in ("disponible", "mantenimiento"):
        return {"exito": False,
                "mensaje": "Estado inválido. Use 'disponible' o 'mantenimiento'. Para 'baja' use el botón Baja."}

    # Si se intenta poner en mantenimiento, validar que no haya préstamos activos
    if estado == "mantenimiento":
        rows = ejecutar_query(
            "SELECT COUNT(*) AS n FROM prestamos WHERE articulo_id = %s AND estado IN ('activo','vencido','pendiente')",
            (articulo_id,),
        )
        if rows and rows[0]["n"] > 0:
            return {"exito": False,
                    "mensaje": "No se puede poner en mantenimiento: el artículo tiene préstamos activos o pendientes."}

    with get_conn() as conn:
        with conn.cursor() as cur:
            if estado:
                cur.execute(
                    """UPDATE articulos
                       SET nombre=%s, descripcion=%s, ubicacion=%s,
                           codigo_barras=%s, tiempo_maximo_minutos=%s, estado=%s::estado_articulo
                       WHERE id=%s AND activo=TRUE""",
                    (nombre, descripcion, ubicacion, codigo_barras,
                     tiempo_maximo_minutos, estado, articulo_id),
                )
            else:
                cur.execute(
                    """UPDATE articulos
                       SET nombre=%s, descripcion=%s, ubicacion=%s,
                           codigo_barras=%s, tiempo_maximo_minutos=%s
                       WHERE id=%s AND activo=TRUE""",
                    (nombre, descripcion, ubicacion, codigo_barras,
                     tiempo_maximo_minutos, articulo_id),
                )
            afectados = cur.rowcount
            if actualizar_multa and afectados:
                cur.execute(
                    "UPDATE articulos SET multa_por_hora_cop = %s WHERE id = %s",
                    (multa_por_hora_cop, articulo_id),
                )
    return {"exito": bool(afectados),
            "mensaje": "Artículo actualizado." if afectados else "No encontrado."}


def formatear_tiempo_maximo(minutos: int | None) -> str:
    """Convierte minutos a formato legible: '7 días', '3 horas', '45 min'."""
    if not minutos:
        return ""
    if minutos % 1440 == 0:
        d = minutos // 1440
        return f"{d} día{'s' if d != 1 else ''}"
    if minutos % 60 == 0:
        h = minutos // 60
        return f"{h} hora{'s' if h != 1 else ''}"
    return f"{minutos} min"


def descomponer_tiempo_maximo(minutos: int | None) -> tuple[int | None, str]:
    """Devuelve (valor, unidad) para precargar formularios.
    unidad ∈ {'minutos', 'horas', 'dias'}
    """
    if not minutos:
        return (None, "dias")
    if minutos % 1440 == 0:
        return (minutos // 1440, "dias")
    if minutos % 60 == 0:
        return (minutos // 60, "horas")
    return (minutos, "minutos")


def calcular_minutos(valor: str, unidad: str) -> int | None:
    """Convierte (valor, unidad) → minutos enteros. Devuelve None si valor vacío."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        n = int(valor)
    except ValueError:
        return None
    if n <= 0:
        return None
    mult = {"minutos": 1, "horas": 60, "dias": 1440}.get(unidad, 1440)
    return n * mult


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
