"""Rutas del portal del estudiante/cliente."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.jwt_handler import requiere_login
from app.services import articulo_service, prestamo_service
from app.templates_config import templates

router = APIRouter()


def _ctx(usuario: dict, **kwargs) -> dict:
    return {"usuario": usuario, **kwargs}


@router.get("/productos", response_class=HTMLResponse)
def productos(request: Request, usuario: dict = Depends(requiere_login),
              buscar: str = "", categoria_id: str = "", msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
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
            f"/cliente/historial?msg=Préstamo+registrado.+Código:+{res['codigo_prestamo']}&tipo=success",
            status_code=302,
        )
    return RedirectResponse(f"/cliente/productos?msg={res['mensaje']}&tipo=error", status_code=302)


@router.get("/historial", response_class=HTMLResponse)
def historial(request: Request, usuario: dict = Depends(requiere_login),
              msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    prestamos = prestamo_service.historial_usuario(int(usuario["sub"]))
    activos  = sum(1 for p in prestamos if str(p.get("estado_prestamo", "")) == "activo")
    vencidos = sum(1 for p in prestamos if str(p.get("estado_prestamo", "")) == "vencido")
    return templates.TemplateResponse(request, "cliente/historial.html", _ctx(
        usuario, prestamos=prestamos,
        total=len(prestamos), activos=activos, vencidos=vencidos,
        msg=msg, tipo=tipo,
    ))
