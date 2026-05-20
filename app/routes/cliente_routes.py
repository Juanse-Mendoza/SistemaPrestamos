"""Rutas del portal del estudiante/cliente."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.jwt_handler import requiere_login
from app.database.connection import ejecutar_query, get_conn
from app.services import articulo_service, prestamo_service
from app.templates_config import templates

router = APIRouter()


def _ctx(usuario: dict, **kwargs) -> dict:
    return {"usuario": usuario, **kwargs}


def _alertas(usuario_id: int) -> dict:
    """Calcula alertas del estudiante: badge de solicitudes y préstamos vencidos con multa."""
    sol = ejecutar_query("""
        SELECT
          (SELECT COUNT(*) FROM prestamos
           WHERE usuario_id = %s AND estado = 'pendiente') +
          (SELECT COUNT(*) FROM devoluciones d
           JOIN prestamos p ON p.id = d.prestamo_id
           WHERE p.usuario_id = %s AND d.confirmada_estudiante IS NULL)
        AS total
    """, (usuario_id, usuario_id))
    solicitudes_count = {"total": int((sol[0]["total"] or 0) if sol else 0)}

    vencidos_raw = ejecutar_query("""
        SELECT p.codigo_prestamo,
               a.nombre AS articulo,
               p.fecha_devolucion_esperada,
               COALESCE(a.multa_por_hora_cop, 1000) AS tasa,
               EXTRACT(EPOCH FROM (NOW() - p.fecha_devolucion_esperada)) / 3600 AS horas_raw,
               COALESCE(p.multa_monto_pagado, 0) AS ya_pagado
        FROM prestamos p
        JOIN articulos a ON a.id = p.articulo_id
        WHERE p.usuario_id = %s AND p.estado = 'vencido'
        ORDER BY p.fecha_devolucion_esperada
    """, (usuario_id,))

    alertas_vencidos = []
    for v in vencidos_raw:
        horas    = max(0, round(float(v.get("horas_raw") or 0), 1))
        tasa     = float(v.get("tasa") or 1000)
        monto    = round(horas * tasa, 0)
        ya_pag   = float(v.get("ya_pagado") or 0)
        saldo    = max(0, monto - ya_pag)
        alertas_vencidos.append({
            "codigo_prestamo":  v["codigo_prestamo"],
            "articulo":         v["articulo"],
            "horas":            horas,
            "multa_saldo_fmt":  f"${saldo:,.0f} COP",
        })

    return {"solicitudes_count": solicitudes_count, "alertas_vencidos": alertas_vencidos}


# ─── Productos ────────────────────────────────────────────────────────────────

@router.get("/productos", response_class=HTMLResponse)
def productos(request: Request, usuario: dict = Depends(requiere_login),
              buscar: str = "", categoria_id: str = "", msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    uid       = int(usuario["sub"])
    alertas   = _alertas(uid)
    articulos  = articulo_service.listar_articulos()
    categorias = articulo_service.listar_categorias()
    if buscar:
        articulos = [a for a in articulos
                     if buscar.lower() in a["articulo"].lower()
                     or buscar.lower() in (a.get("descripcion") or "").lower()]
    if categoria_id:
        articulos = [a for a in articulos if str(a.get("categoria_id", "")) == categoria_id]
    return templates.TemplateResponse(request, "cliente/productos.html", _ctx(
        usuario, articulos=articulos, categorias=categorias,
        buscar=buscar, categoria_id=categoria_id, msg=msg, tipo=tipo,
        **alertas,
    ))


@router.post("/prestamos/solicitar")
def solicitar_prestamo(usuario: dict = Depends(requiere_login),
                        articulo_id: int = Form(...),
                        fecha_devolucion: str = Form(...),
                        observaciones: str = Form("")):
    try:
        fecha_dev = datetime.fromisoformat(fecha_devolucion)
    except ValueError:
        return RedirectResponse("/cliente/productos?msg=Fecha+invalida&tipo=error", status_code=302)
    res = prestamo_service.registrar_prestamo(
        int(usuario["sub"]), articulo_id, fecha_dev, None, observaciones or None
    )
    if res["exito"]:
        return RedirectResponse(
            f"/cliente/solicitudes?msg=Solicitud+enviada.+Código:+{res['codigo_prestamo']}&tipo=success",
            status_code=302,
        )
    return RedirectResponse(f"/cliente/productos?msg={res['mensaje']}&tipo=error", status_code=302)


# ─── Historial ────────────────────────────────────────────────────────────────

@router.get("/historial", response_class=HTMLResponse)
def historial(request: Request, usuario: dict = Depends(requiere_login),
              msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    uid      = int(usuario["sub"])
    alertas  = _alertas(uid)
    prestamos = prestamo_service.historial_usuario(uid)
    activos  = sum(1 for p in prestamos if str(p.get("estado_prestamo", "")) == "activo")
    vencidos = sum(1 for p in prestamos if str(p.get("estado_prestamo", "")) == "vencido")
    return templates.TemplateResponse(request, "cliente/historial.html", _ctx(
        usuario, prestamos=prestamos,
        total=len(prestamos), activos=activos, vencidos=vencidos,
        msg=msg, tipo=tipo,
        **alertas,
    ))


# ─── Solicitudes (confirmación de préstamos y devoluciones) ──────────────────

@router.get("/solicitudes", response_class=HTMLResponse)
def solicitudes(request: Request, usuario: dict = Depends(requiere_login),
                msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    uid = int(usuario["sub"])

    pendientes = ejecutar_query("""
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               a.nombre AS articulo, a.descripcion AS descripcion_articulo,
               cat.nombre AS categoria, a.ubicacion,
               p.fecha_prestamo, p.fecha_devolucion_esperada, p.observaciones
        FROM prestamos p
        JOIN articulos a ON a.id = p.articulo_id
        LEFT JOIN categorias cat ON cat.id = a.categoria_id
        WHERE p.usuario_id = %s AND p.estado = 'pendiente'
        ORDER BY p.fecha_prestamo DESC
    """, (uid,))

    dev_pendientes = ejecutar_query("""
        SELECT d.id AS devolucion_id, p.codigo_prestamo,
               a.nombre AS articulo,
               u.nombre || ' ' || u.apellido AS admin_recibe,
               d.fecha_devolucion, d.estado_articulo_recibido, d.observaciones
        FROM devoluciones d
        JOIN prestamos p ON p.id = d.prestamo_id
        JOIN articulos a ON a.id = p.articulo_id
        LEFT JOIN usuarios u ON u.id = d.administrador_recibe_id
        WHERE p.usuario_id = %s AND d.confirmada_estudiante IS NULL
        ORDER BY d.fecha_devolucion DESC
    """, (uid,))

    alertas = _alertas(uid)
    solicitudes_count = {"total": len(pendientes) + len(dev_pendientes)}

    return templates.TemplateResponse(request, "cliente/solicitudes.html", _ctx(
        usuario,
        pendientes=pendientes,
        dev_pendientes=dev_pendientes,
        solicitudes_count=solicitudes_count,
        msg=msg, tipo=tipo,
        alertas_vencidos=alertas["alertas_vencidos"],
    ))


@router.post("/prestamos/{prestamo_id}/aceptar")
def aceptar_prestamo(prestamo_id: int, usuario: dict = Depends(requiere_login),
                     motivo: str = Form("")):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_aceptar_prestamo(%s::integer, %s::integer, %s, NULL)",
                        (prestamo_id, int(usuario["sub"]), motivo or None))
            row = cur.fetchone()
    msg  = row["p_mensaje"] if row else "Procesado."
    tipo = "success" if "exitosamente" in (msg or "").lower() else "error"
    return RedirectResponse(f"/cliente/solicitudes?msg={msg}&tipo={tipo}", status_code=302)


@router.post("/prestamos/{prestamo_id}/rechazar")
def rechazar_prestamo(prestamo_id: int, usuario: dict = Depends(requiere_login),
                      motivo: str = Form("")):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_rechazar_prestamo(%s::integer, %s::integer, %s, NULL)",
                        (prestamo_id, int(usuario["sub"]), motivo or "Sin motivo especificado"))
            row = cur.fetchone()
    msg  = row["p_mensaje"] if row else "Procesado."
    tipo = "success" if "rechazado" in (msg or "").lower() else "error"
    return RedirectResponse(f"/cliente/solicitudes?msg={msg}&tipo={tipo}", status_code=302)


@router.post("/devoluciones/{devolucion_id}/confirmar")
def confirmar_devolucion(devolucion_id: int, usuario: dict = Depends(requiere_login),
                          motivo: str = Form("")):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_confirmar_devolucion(%s::integer, %s::integer, NULL)",
                        (devolucion_id, int(usuario["sub"])))
            row = cur.fetchone()
    msg  = row["p_mensaje"] if row else "Procesado."
    tipo = "success" if "exitosamente" in (msg or "").lower() else "error"
    return RedirectResponse(f"/cliente/solicitudes?msg={msg}&tipo={tipo}", status_code=302)


@router.post("/devoluciones/{devolucion_id}/rechazar")
def rechazar_devolucion(devolucion_id: int, usuario: dict = Depends(requiere_login),
                         motivo: str = Form(...)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_rechazar_devolucion(%s::integer, %s::integer, %s, NULL)",
                        (devolucion_id, int(usuario["sub"]), motivo))
            row = cur.fetchone()
    msg  = row["p_mensaje"] if row else "Procesado."
    tipo = "success" if "disputa" in (msg or "").lower() else "error"
    return RedirectResponse(f"/cliente/solicitudes?msg={msg}&tipo={tipo}", status_code=302)
