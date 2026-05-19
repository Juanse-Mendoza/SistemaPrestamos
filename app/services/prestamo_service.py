from __future__ import annotations

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
    if row and row["p_prestamo_id"] and row["p_prestamo_id"] > 0:
        return {"exito": True, "prestamo_id": row["p_prestamo_id"],
                "codigo_prestamo": row["p_codigo_prestamo"], "mensaje": row["p_mensaje"]}
    return {"exito": False, "mensaje": row["p_mensaje"] if row else "Error."}


def registrar_devolucion(prestamo_id: int, estado_articulo: str,
                          admin_id: int | None, observaciones: str | None) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_devolucion(%s,%s::estado_articulo,%s,%s,NULL,NULL)",
                (prestamo_id, estado_articulo, admin_id, observaciones),
            )
            row = cur.fetchone()
    if row and row["p_devolucion_id"] and row["p_devolucion_id"] > 0:
        return {"exito": True, "mensaje": row["p_mensaje"]}
    return {"exito": False, "mensaje": row["p_mensaje"] if row else "Error."}


def listar_prestamos_activos() -> list[dict]:
    return ejecutar_query("SELECT * FROM v_prestamos_activos")


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
