"""Rutas del panel administrador."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth.jwt_handler import requiere_admin
from app.services import articulo_service, prestamo_service
from app.services.auth_service import registrar_usuario_admin
from app.templates_config import templates

router = APIRouter()


def _ctx(usuario: dict, **kwargs) -> dict:
    return {"usuario": usuario, **kwargs}


# ─── API interna ──────────────────────────────────────────────────────────────

@router.get("/api/buscar-barcode/{codigo}")
def api_buscar_barcode(codigo: str, usuario: dict = Depends(requiere_admin)):
    """Verifica si un código de barras ya existe en el sistema."""
    from app.database.connection import ejecutar_query
    rows = ejecutar_query(
        "SELECT articulo_id, articulo, estado, stock_disponible FROM v_stock_disponible WHERE codigo_barras = %s",
        (codigo,)
    )
    if rows:
        return JSONResponse({"existe": True, "articulo": rows[0]})
    return JSONResponse({"existe": False})


@router.get("/api/articulos-disponibles")
def api_articulos_disponibles(usuario: dict = Depends(requiere_admin)):
    arts = articulo_service.listar_articulos(solo_disponibles=True)
    return JSONResponse([
        {"articulo_id": a["articulo_id"], "articulo": a["articulo"],
         "stock_disponible": a["stock_disponible"]}
        for a in arts
    ])


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, usuario: dict = Depends(requiere_admin)):
    prestamo_service.actualizar_prestamos_vencidos()
    return templates.TemplateResponse(request, "admin/dashboard.html", _ctx(
        usuario,
        metricas=prestamo_service.metricas_reporte(),
        prestamos=prestamo_service.listar_prestamos_activos(),
    ))


# ─── Productos ────────────────────────────────────────────────────────────────

@router.get("/productos", response_class=HTMLResponse)
def productos(request: Request, usuario: dict = Depends(requiere_admin),
              msg: str = "", tipo: str = ""):
    return templates.TemplateResponse(request, "admin/productos.html", _ctx(
        usuario,
        articulos=articulo_service.listar_articulos(),
        categorias=articulo_service.listar_categorias(),
        msg=msg, tipo=tipo,
    ))


@router.post("/productos/nuevo")
def nuevo_producto(usuario: dict = Depends(requiere_admin),
                   nombre: str = Form(...), descripcion: str = Form(""),
                   categoria_id: str = Form(""), stock_total: int = Form(...),
                   codigo_interno: str = Form(""), ubicacion: str = Form(""),
                   codigo_barras: str = Form("")):
    res = articulo_service.registrar_articulo(
        nombre, descripcion or None,
        int(categoria_id) if categoria_id else None,
        stock_total, codigo_interno or None, ubicacion or None,
        codigo_barras.strip() or None,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/productos?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/productos/{articulo_id}/editar")
def editar_producto(articulo_id: int, usuario: dict = Depends(requiere_admin),
                    nombre: str = Form(...), descripcion: str = Form(""),
                    ubicacion: str = Form("")):
    res = articulo_service.actualizar_articulo(articulo_id, nombre,
                                                descripcion or None, ubicacion or None)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/productos?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/productos/{articulo_id}/stock")
def cambiar_stock(articulo_id: int, usuario: dict = Depends(requiere_admin),
                  nuevo_stock: int = Form(...)):
    res = articulo_service.actualizar_stock(articulo_id, nuevo_stock)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/productos?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/productos/{articulo_id}/baja")
def baja_producto(articulo_id: int, usuario: dict = Depends(requiere_admin),
                  motivo: str = Form(...)):
    res = articulo_service.dar_baja_articulo(articulo_id, motivo)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/productos?msg={res['mensaje']}&tipo={tipo}", status_code=302)


# ─── Historial ────────────────────────────────────────────────────────────────

@router.get("/historial", response_class=HTMLResponse)
def historial(request: Request, usuario: dict = Depends(requiere_admin),
              desde: str = "", hasta: str = "", msg: str = "", tipo: str = ""):
    try:
        fi = datetime.fromisoformat(desde) if desde else datetime.now() - timedelta(days=30)
        ff = datetime.fromisoformat(hasta) if hasta else datetime.now()
    except ValueError:
        fi = datetime.now() - timedelta(days=30); ff = datetime.now()
    return templates.TemplateResponse(request, "admin/historial.html", _ctx(
        usuario,
        prestamos=prestamo_service.historial_completo(fi, ff),
        articulos=articulo_service.listar_articulos(),
        desde=fi.date(), hasta=ff.date(), msg=msg, tipo=tipo,
    ))


@router.post("/prestamos/nuevo")
def nuevo_prestamo(usuario: dict = Depends(requiere_admin),
                   usuario_correo: str = Form(...), articulo_id: int = Form(...),
                   fecha_devolucion: str = Form(...), observaciones: str = Form("")):
    from app.database.connection import ejecutar_query
    rows = ejecutar_query("SELECT id FROM usuarios WHERE correo=%s AND activo=TRUE",
                          (usuario_correo.lower(),))
    if not rows:
        return RedirectResponse(
            f"/admin/historial?msg=Usuario+no+encontrado&tipo=error", status_code=302
        )
    try:
        fecha_dev = datetime.fromisoformat(fecha_devolucion)
    except ValueError:
        return RedirectResponse("/admin/historial?msg=Fecha+invalida&tipo=error", status_code=302)
    res = prestamo_service.registrar_prestamo(
        rows[0]["id"], articulo_id, fecha_dev, int(usuario["sub"]), observaciones or None
    )
    tipo = "success" if res["exito"] else "error"
    msg = res.get("codigo_prestamo", res["mensaje"]) if res["exito"] else res["mensaje"]
    return RedirectResponse(f"/admin/historial?msg={msg}&tipo={tipo}", status_code=302)


@router.post("/prestamos/{prestamo_id}/devolver")
def devolver(prestamo_id: int, usuario: dict = Depends(requiere_admin),
             estado_articulo: str = Form(...), observaciones: str = Form("")):
    res = prestamo_service.registrar_devolucion(
        prestamo_id, estado_articulo, int(usuario["sub"]), observaciones or None
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/historial?msg={res['mensaje']}&tipo={tipo}", status_code=302)


# ─── Usuarios ─────────────────────────────────────────────────────────────────

@router.get("/usuarios", response_class=HTMLResponse)
def usuarios(request: Request, usuario: dict = Depends(requiere_admin),
             msg: str = "", tipo: str = ""):
    return templates.TemplateResponse(request, "admin/usuarios.html", _ctx(
        usuario,
        usuarios=prestamo_service.listar_usuarios(),
        msg=msg, tipo=tipo,
    ))


@router.post("/usuarios/nuevo")
def nuevo_usuario(usuario: dict = Depends(requiere_admin),
                  nombre: str = Form(...), apellido: str = Form(...),
                  correo: str = Form(...), documento: str = Form(""),
                  password: str = Form(...), rol: str = Form(...)):
    res = registrar_usuario_admin(nombre, apellido, correo.strip(), password, rol,
                                   documento.strip() or None)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/usuarios?msg={res['mensaje']}&tipo={tipo}", status_code=302)
