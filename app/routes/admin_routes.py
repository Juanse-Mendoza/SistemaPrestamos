"""Rutas del panel administrador."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from typing import List, Optional

from app.auth.jwt_handler import requiere_admin
from app.services import articulo_service, prestamo_service, reporte_service
from app.services.auth_service import (
    registrar_usuario_admin, actualizar_usuario, generar_codigo_barras_usuario
)
from app.templates_config import templates

router = APIRouter()


def _ctx(usuario: dict, **kwargs) -> dict:
    multas_pendientes = prestamo_service.listar_multas_pendientes_admin()
    return {
        "usuario": usuario,
        "solicitudes_count": prestamo_service.contar_solicitudes_admin(),
        "multas_count": len(multas_pendientes),
        **kwargs,
    }


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


@router.get("/api/buscar-prestamo-barcode/{codigo}")
def api_buscar_prestamo_barcode(codigo: str, usuario: dict = Depends(requiere_admin)):
    """Busca un préstamo en curso (activo o vencido) por el código de barras del artículo."""
    from app.database.connection import ejecutar_query
    rows = ejecutar_query(
        """
        SELECT p.id              AS prestamo_id,
               p.codigo_prestamo,
               p.estado,
               u.nombre || ' ' || u.apellido AS estudiante,
               u.correo                       AS correo,
               a.nombre                       AS articulo
        FROM prestamos p
        INNER JOIN articulos a ON a.id = p.articulo_id
        INNER JOIN usuarios u  ON u.id = p.usuario_id
        WHERE a.codigo_barras = %s
          AND p.estado IN ('activo', 'vencido')
        ORDER BY p.fecha_prestamo DESC
        LIMIT 1
        """,
        (codigo,),
    )
    if not rows:
        # Verificar si existe el artículo aunque no tenga préstamo
        art = ejecutar_query(
            "SELECT id, nombre FROM articulos WHERE codigo_barras = %s",
            (codigo,),
        )
        if not art:
            return JSONResponse({
                "encontrado": False,
                "razon": "codigo_inexistente",
                "mensaje": f"No se tienen reservas con el código de barras «{codigo}». Este código no está registrado en el sistema.",
            })
        return JSONResponse({
            "encontrado": False,
            "razon": "sin_prestamo",
            "articulo": art[0]["nombre"],
            "mensaje": f"No se tienen reservas activas con ese código de barras. El artículo «{art[0]['nombre']}» existe pero no está prestado actualmente.",
        })
    return JSONResponse({"encontrado": True, "prestamo": rows[0]})


@router.get("/api/buscar-articulo-barcode/{codigo}")
def api_buscar_articulo_barcode(codigo: str, usuario: dict = Depends(requiere_admin)):
    """Busca un artículo por código de barras para selección rápida."""
    from app.database.connection import ejecutar_query
    rows = ejecutar_query(
        """
        SELECT articulo_id, articulo, descripcion, estado, stock_disponible, stock_total, tiempo_maximo_minutos
        FROM v_stock_disponible
        WHERE codigo_barras = %s
        """,
        (codigo,),
    )
    if not rows:
        return JSONResponse({
            "encontrado": False,
            "mensaje": f"No se encontró ningún artículo con el código «{codigo}».",
        })
    a = rows[0]
    if a["estado"] != "disponible" or a["stock_disponible"] <= 0:
        return JSONResponse({
            "encontrado": True, "disponible": False,
            "articulo": a,
            "mensaje": f"«{a['articulo']}» existe pero no está disponible (estado: {a['estado']}, stock: {a['stock_disponible']}).",
        })
    return JSONResponse({"encontrado": True, "disponible": True, "articulo": a})


@router.get("/api/buscar-usuario-barcode/{codigo}")
def api_buscar_usuario_barcode(codigo: str, usuario: dict = Depends(requiere_admin)):
    """Busca un usuario (cliente) por código de barras del carnet/perfil."""
    from app.database.connection import ejecutar_query
    rows = ejecutar_query(
        """
        SELECT u.id, u.nombre, u.apellido, u.correo, u.numero_documento, u.activo, r.nombre AS rol
        FROM usuarios u
        INNER JOIN roles r ON r.id = u.rol_id
        WHERE u.codigo_barras = %s
        """,
        (codigo,),
    )
    if not rows:
        return JSONResponse({
            "encontrado": False,
            "mensaje": f"No se encontró ningún estudiante con el código «{codigo}».",
        })
    u = rows[0]
    if not u["activo"]:
        return JSONResponse({
            "encontrado": True, "activo": False,
            "mensaje": f"El estudiante «{u['nombre']} {u['apellido']}» está desactivado.",
        })
    return JSONResponse({
        "encontrado": True, "activo": True,
        "usuario": {
            "id": u["id"],
            "nombre": f"{u['nombre']} {u['apellido']}",
            "correo": u["correo"],
            "documento": u["numero_documento"] or "",
            "rol": u["rol"],
        },
    })


@router.get("/api/articulos-disponibles")
def api_articulos_disponibles(usuario: dict = Depends(requiere_admin)):
    arts = articulo_service.listar_articulos(solo_disponibles=True)
    return JSONResponse([
        {"articulo_id": a["articulo_id"], "articulo": a["articulo"],
         "stock_disponible": a["stock_disponible"],
         "tiempo_maximo_minutos": a.get("tiempo_maximo_minutos"),
         "tiempo_maximo_legible": articulo_service.formatear_tiempo_maximo(a.get("tiempo_maximo_minutos"))}
        for a in arts
    ])


# ─── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, usuario: dict = Depends(requiere_admin),
              msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    return templates.TemplateResponse(request, "admin/dashboard.html", _ctx(
        usuario,
        metricas=prestamo_service.metricas_reporte(),
        prestamos=prestamo_service.listar_prestamos_en_curso(),
        msg=msg, tipo=tipo,
    ))


@router.get("/solicitudes", response_class=HTMLResponse)
def solicitudes(request: Request, usuario: dict = Depends(requiere_admin),
                msg: str = "", tipo: str = ""):
    return templates.TemplateResponse(request, "admin/solicitudes.html", _ctx(
        usuario,
        pendientes=prestamo_service.listar_pendientes_todos(),
        disputas=prestamo_service.listar_devoluciones_disputa(),
        msg=msg, tipo=tipo,
    ))


@router.get("/disputas", response_class=HTMLResponse)
def disputas_historial(request: Request, usuario: dict = Depends(requiere_admin),
                        estado: str = "", desde: str = "", hasta: str = "",
                        msg: str = "", tipo: str = ""):
    fi = None
    ff = None
    try:
        fi = datetime.fromisoformat(desde) if desde else None
        ff = datetime.fromisoformat(hasta) if hasta else None
    except ValueError:
        pass
    estado_filtro = estado if estado in ("activa", "cerrada", "corregida") else None
    rows = prestamo_service.historial_disputas(estado_filtro, fi, ff)
    # Conteos para resumen
    total    = len(rows)
    activas  = sum(1 for r in rows if r["estado_disputa"] == "activa")
    cerradas = sum(1 for r in rows if r["estado_disputa"] == "cerrada")
    corregidas = sum(1 for r in rows if r["estado_disputa"] == "corregida")
    return templates.TemplateResponse(request, "admin/disputas.html", _ctx(
        usuario, disputas=rows,
        total=total, activas=activas, cerradas=cerradas, corregidas=corregidas,
        estado=estado, desde=desde, hasta=hasta,
        msg=msg, tipo=tipo,
    ))


@router.get("/api/solicitudes/prestamo/{prestamo_id}")
def api_detalle_pendiente(prestamo_id: int, usuario: dict = Depends(requiere_admin)):
    det = prestamo_service.obtener_pendiente_detalle(prestamo_id)
    if not det:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    return JSONResponse({
        "prestamo_id":    det["prestamo_id"],
        "codigo":         det["codigo_prestamo"],
        "estudiante":     det["usuario_nombre"],
        "correo":         det["usuario_correo"],
        "documento":      det["numero_documento"] or "",
        "articulo":       det["articulo"],
        "categoria":      det["categoria"] or "",
        "ubicacion":      det["ubicacion"] or "",
        "codigo_interno": det["codigo_interno"] or "",
        "fecha_prestamo": det["fecha_prestamo"].strftime("%Y-%m-%d %H:%M") if det["fecha_prestamo"] else "",
        "fecha_dev_esp":  det["fecha_devolucion_esperada"].strftime("%Y-%m-%d %H:%M") if det["fecha_devolucion_esperada"] else "",
        "observaciones":  det["observaciones"] or "",
    })


@router.get("/api/solicitudes/disputa/{devolucion_id}")
def api_detalle_disputa(devolucion_id: int, usuario: dict = Depends(requiere_admin)):
    det = prestamo_service.obtener_disputa_detalle(devolucion_id)
    if not det:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    return JSONResponse({
        "devolucion_id":  det["devolucion_id"],
        "codigo":         det["codigo_prestamo"],
        "estudiante":     det["usuario_nombre"],
        "correo":         det["usuario_correo"],
        "articulo":       det["articulo"],
        "admin_recibio":  det["admin_recibio"] or "",
        "estado":         det["estado_articulo_recibido"],
        "fecha_devolucion": det["fecha_devolucion"].strftime("%Y-%m-%d %H:%M") if det["fecha_devolucion"] else "",
        "fecha_prestamo":   det["fecha_prestamo"].strftime("%Y-%m-%d %H:%M") if det["fecha_prestamo"] else "",
        "fecha_dev_esp":    det["fecha_devolucion_esperada"].strftime("%Y-%m-%d %H:%M") if det["fecha_devolucion_esperada"] else "",
        "fecha_rechazo":    det["fecha_confirmacion"].strftime("%Y-%m-%d %H:%M") if det["fecha_confirmacion"] else "",
        "observaciones":  det["observaciones"] or "",
        "motivo_rechazo": det["motivo_rechazo"] or "",
    })


@router.get("/api/disputas/{devolucion_id}")
def api_detalle_disputa_hist(devolucion_id: int,
                              usuario: dict = Depends(requiere_admin)):
    det = prestamo_service.obtener_disputa_cualquier_estado(devolucion_id)
    if not det:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    if det["confirmada_estudiante"] is False:
        estado_disputa = "activa"
    elif det["confirmada_estudiante"] is True:
        estado_disputa = "cerrada"
    else:
        estado_disputa = "corregida"
    return JSONResponse({
        "devolucion_id":  det["devolucion_id"],
        "codigo":         det["codigo_prestamo"],
        "estudiante":     det["usuario_nombre"],
        "correo":         det["usuario_correo"],
        "articulo":       det["articulo"],
        "admin_recibio":  det["admin_recibio"] or "",
        "estado":         det["estado_articulo_recibido"],
        "estado_disputa": estado_disputa,
        "fecha_devolucion": det["fecha_devolucion"].strftime("%Y-%m-%d %H:%M") if det["fecha_devolucion"] else "",
        "fecha_resolucion": det["fecha_confirmacion"].strftime("%Y-%m-%d %H:%M") if det["fecha_confirmacion"] else "",
        "observaciones":  det["observaciones"] or "",
        "motivo_rechazo": det["motivo_rechazo"] or "",
    })


@router.post("/solicitudes/prestamos/{prestamo_id}/cancelar")
def cancelar_pendiente(prestamo_id: int, usuario: dict = Depends(requiere_admin),
                       motivo: str = Form("")):
    motivo = motivo.strip()
    if not motivo:
        return RedirectResponse(
            "/admin/solicitudes?msg=Debe+indicar+el+motivo+de+la+cancelación&tipo=error",
            status_code=302,
        )
    res = prestamo_service.cancelar_prestamo_pendiente(prestamo_id, int(usuario["sub"]), motivo)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/solicitudes?msg={res['mensaje']}&tipo={tipo}",
                             status_code=302)


@router.post("/solicitudes/disputas/{devolucion_id}/corregir")
def corregir_disputa(devolucion_id: int, usuario: dict = Depends(requiere_admin),
                     nuevo_estado: str = Form(...),
                     nuevas_observaciones: str = Form(""),
                     nota_admin: str = Form(...)):
    nota = nota_admin.strip()
    if not nota:
        return RedirectResponse(
            "/admin/solicitudes?msg=Debe+indicar+una+nota+explicando+la+corrección&tipo=error",
            status_code=302,
        )
    res = prestamo_service.corregir_devolucion(
        devolucion_id, int(usuario["sub"]),
        nuevo_estado, nuevas_observaciones.strip() or None, nota,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/solicitudes?msg={res['mensaje']}&tipo={tipo}",
                             status_code=302)


@router.post("/solicitudes/disputas/{devolucion_id}/cerrar")
def cerrar_disputa_admin(devolucion_id: int, usuario: dict = Depends(requiere_admin),
                          nota: str = Form(...)):
    nota = nota.strip()
    if not nota:
        return RedirectResponse(
            "/admin/solicitudes?msg=Debe+indicar+la+nota+de+cierre&tipo=error",
            status_code=302,
        )
    res = prestamo_service.cerrar_disputa(devolucion_id, int(usuario["sub"]), nota)
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/solicitudes?msg={res['mensaje']}&tipo={tipo}",
                             status_code=302)


# ─── Productos ────────────────────────────────────────────────────────────────

@router.get("/productos", response_class=HTMLResponse)
def productos(request: Request, usuario: dict = Depends(requiere_admin),
              buscar: str = "", msg: str = "", tipo: str = ""):
    articulos = articulo_service.listar_articulos()
    if buscar:
        q = buscar.strip().lower()
        articulos = [
            a for a in articulos
            if q in (a.get("articulo") or "").lower()
            or q in (a.get("codigo_barras") or "").lower()
            or q in (a.get("codigo_interno") or "").lower()
        ]
    # Enriquecer con tiempo legible y descompuesto (para precargar el form de edición)
    for a in articulos:
        mins = a.get("tiempo_maximo_minutos")
        a["tiempo_maximo_legible"] = articulo_service.formatear_tiempo_maximo(mins)
        valor, unidad = articulo_service.descomponer_tiempo_maximo(mins)
        a["tiempo_maximo_valor"]  = valor
        a["tiempo_maximo_unidad"] = unidad
    return templates.TemplateResponse(request, "admin/productos.html", _ctx(
        usuario,
        articulos=articulos,
        categorias=articulo_service.listar_categorias(),
        buscar=buscar, msg=msg, tipo=tipo,
    ))


def _parse_multa_hora(valor: str) -> float | None:
    v = (valor or "").strip()
    if not v:
        return None
    try:
        f = float(v)
        return f if f >= 0 else None
    except ValueError:
        return None


@router.post("/productos/nuevo")
def nuevo_producto(usuario: dict = Depends(requiere_admin),
                   nombre: str = Form(...), descripcion: str = Form(""),
                   categoria_id: str = Form(""), stock_total: int = Form(...),
                   codigo_interno: str = Form(""), ubicacion: str = Form(""),
                   codigo_barras: str = Form(""),
                   tiempo_maximo_valor: str = Form(""),
                   tiempo_maximo_unidad: str = Form("dias"),
                   multa_por_hora_cop: str = Form("")):
    minutos = articulo_service.calcular_minutos(tiempo_maximo_valor, tiempo_maximo_unidad)
    res = articulo_service.registrar_articulo(
        nombre, descripcion or None,
        int(categoria_id) if categoria_id else None,
        stock_total, codigo_interno or None, ubicacion or None,
        codigo_barras.strip() or None, minutos,
        _parse_multa_hora(multa_por_hora_cop),
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/productos?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/productos/{articulo_id}/editar")
def editar_producto(articulo_id: int, usuario: dict = Depends(requiere_admin),
                    nombre: str = Form(...), descripcion: str = Form(""),
                    ubicacion: str = Form(""), codigo_barras: str = Form(""),
                    tiempo_maximo_valor: str = Form(""),
                    tiempo_maximo_unidad: str = Form("dias"),
                    estado: str = Form(""),
                    multa_por_hora_cop: str = Form("")):
    minutos = articulo_service.calcular_minutos(tiempo_maximo_valor, tiempo_maximo_unidad)
    res = articulo_service.actualizar_articulo(
        articulo_id, nombre,
        descripcion or None, ubicacion or None,
        codigo_barras.strip() or None, minutos,
        estado.strip() or None,
        _parse_multa_hora(multa_por_hora_cop),
        actualizar_multa=True,
    )
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
async def nuevo_prestamo(request: Request, usuario: dict = Depends(requiere_admin)):
    from app.database.connection import ejecutar_query
    form = await request.form()
    usuario_correo = (form.get("usuario_correo") or "").strip().lower()
    observaciones  = (form.get("observaciones") or "").strip() or None

    rows = ejecutar_query(
        "SELECT id FROM usuarios WHERE correo=%s AND activo=TRUE", (usuario_correo,)
    )
    if not rows:
        return RedirectResponse(
            "/admin/historial?msg=Usuario+no+encontrado&tipo=error", status_code=302
        )
    usuario_id = rows[0]["id"]

    # Recolectar hasta 2 artículos + fechas
    items = []
    for i in (1, 2):
        art_id   = (form.get(f"articulo_id_{i}") or "").strip()
        fecha_str = (form.get(f"fecha_devolucion_{i}") or "").strip()
        if not art_id:
            continue
        if not fecha_str:
            return RedirectResponse(
                f"/admin/historial?msg=Falta+la+fecha+del+artículo+{i}&tipo=error",
                status_code=302,
            )
        try:
            fecha_dev = datetime.fromisoformat(fecha_str)
        except ValueError:
            return RedirectResponse(
                f"/admin/historial?msg=Fecha+inválida+en+artículo+{i}&tipo=error",
                status_code=302,
            )
        items.append({"articulo_id": int(art_id), "fecha_devolucion": fecha_dev})

    # Compatibilidad con formularios antiguos que envían 'articulo_id' / 'fecha_devolucion'
    if not items:
        legacy_id    = (form.get("articulo_id") or "").strip()
        legacy_fecha = (form.get("fecha_devolucion") or "").strip()
        if legacy_id and legacy_fecha:
            try:
                items.append({
                    "articulo_id": int(legacy_id),
                    "fecha_devolucion": datetime.fromisoformat(legacy_fecha),
                })
            except ValueError:
                return RedirectResponse(
                    "/admin/historial?msg=Fecha+inválida&tipo=error", status_code=302,
                )

    if not items:
        return RedirectResponse(
            "/admin/historial?msg=Debe+seleccionar+al+menos+un+artículo&tipo=error",
            status_code=302,
        )

    res = prestamo_service.registrar_prestamo_multiple(
        usuario_id, int(usuario["sub"]), items, observaciones,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/historial?msg={res['mensaje']}&tipo={tipo}",
                             status_code=302)


CHECKLIST_ITEMS_DEVOLUCION = [
    ("funciona",      "Funcionamiento correcto"),
    ("sin_danos",     "Sin daños visibles ni golpes"),
    ("accesorios",    "Accesorios completos"),
    ("empaque",       "Empaque / embalaje en buen estado"),
    ("limpieza",      "Limpieza adecuada"),
]


def _construir_observaciones_devolucion(
    checklist_ok: list[str], estado_articulo: str,
    observaciones_extra: str
) -> str:
    """Consolida checklist + estado + observaciones en un único texto."""
    lineas = ["=== CHECKLIST DE DEVOLUCIÓN ==="]
    for clave, etiqueta in CHECKLIST_ITEMS_DEVOLUCION:
        marca = "[OK]" if clave in checklist_ok else "[X]"
        lineas.append(f"{marca} {etiqueta}")
    lineas.append("")
    lineas.append(f"ESTADO DECLARADO: {estado_articulo}")
    if observaciones_extra:
        lineas.append("")
        lineas.append("OBSERVACIONES ADICIONALES:")
        lineas.append(observaciones_extra.strip())
    return "\n".join(lineas)


@router.post("/prestamos/{prestamo_id}/devolver")
async def devolver(prestamo_id: int, request: Request,
                   usuario: dict = Depends(requiere_admin)):
    form = await request.form()
    estado_articulo  = form.get("estado_articulo") or ""
    observaciones    = (form.get("observaciones") or "").strip()
    fecha_str        = (form.get("fecha_devolucion") or "").strip()
    redirigir        = form.get("redirigir") or "historial"
    checklist_ok     = form.getlist("checklist")
    destino          = "dashboard" if redirigir == "dashboard" else "historial"

    if not estado_articulo:
        return RedirectResponse(
            f"/admin/{destino}?msg=Debe+seleccionar+el+estado+del+artículo&tipo=error",
            status_code=302,
        )

    fecha_devolucion = None
    if fecha_str:
        try:
            fecha_devolucion = datetime.fromisoformat(fecha_str)
        except ValueError:
            return RedirectResponse(
                f"/admin/{destino}?msg=Fecha+de+devolución+inválida&tipo=error",
                status_code=302,
            )

    obs_consolidadas = _construir_observaciones_devolucion(
        checklist_ok, estado_articulo, observaciones
    )

    res = prestamo_service.registrar_devolucion(
        prestamo_id, estado_articulo, int(usuario["sub"]),
        obs_consolidadas, fecha_devolucion,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/{destino}?msg={res['mensaje']}&tipo={tipo}", status_code=302)


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
                  password: str = Form(...), rol: str = Form(...),
                  codigo_barras: str = Form("")):
    res = registrar_usuario_admin(
        nombre, apellido, correo.strip(), password, rol,
        documento.strip() or None, codigo_barras.strip() or None,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/usuarios?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/usuarios/{usuario_id}/editar")
def editar_usuario(usuario_id: int, usuario: dict = Depends(requiere_admin),
                   nombre: str = Form(...), apellido: str = Form(...),
                   correo: str = Form(...), documento: str = Form(""),
                   codigo_barras: str = Form(""), activo: str = Form(""),
                   password: str = Form("")):
    res = actualizar_usuario(
        usuario_id, nombre, apellido, correo,
        documento.strip() or None,
        codigo_barras.strip() or None,
        activo == "on",
        password.strip() or None,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/usuarios?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.get("/api/generar-codigo-usuario")
def api_generar_codigo_usuario(usuario: dict = Depends(requiere_admin)):
    """Devuelve un código de barras único para un nuevo usuario."""
    return JSONResponse({"codigo": generar_codigo_barras_usuario()})


# ─── Multas ───────────────────────────────────────────────────────────────────

@router.get("/multas", response_class=HTMLResponse)
def multas(request: Request, usuario: dict = Depends(requiere_admin),
           msg: str = "", tipo: str = ""):
    prestamo_service.actualizar_prestamos_vencidos()
    return templates.TemplateResponse(request, "admin/multas.html", _ctx(
        usuario,
        multas=prestamo_service.listar_multas_pendientes_admin(),
        msg=msg, tipo=tipo,
    ))


@router.post("/multas/{prestamo_id}/pagar")
def pagar_multa(prestamo_id: int, usuario: dict = Depends(requiere_admin),
                monto: str = Form(""), observaciones: str = Form("")):
    try:
        monto_int = int(monto) if monto.strip() else 0
    except ValueError:
        monto_int = 0
    res = prestamo_service.registrar_pago_multa(
        prestamo_id, int(usuario["sub"]), monto_int,
        observaciones.strip() or None,
    )
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/multas?msg={res['mensaje']}&tipo={tipo}",
                             status_code=302)


# ─── Reportes PDF ─────────────────────────────────────────────────────────────

def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/reportes/productos.pdf")
def reporte_productos_pdf(usuario: dict = Depends(requiere_admin),
                           buscar: str = ""):
    articulos = articulo_service.listar_articulos()
    if buscar:
        q = buscar.strip().lower()
        articulos = [
            a for a in articulos
            if q in (a.get("articulo") or "").lower()
            or q in (a.get("codigo_barras") or "").lower()
            or q in (a.get("codigo_interno") or "").lower()
        ]
    pdf = reporte_service.reporte_productos(articulos)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    return _pdf_response(pdf, f"productos_{fecha}.pdf")


@router.get("/reportes/usuarios.pdf")
def reporte_usuarios_pdf(usuario: dict = Depends(requiere_admin)):
    usuarios = prestamo_service.listar_usuarios()
    pdf = reporte_service.reporte_usuarios(usuarios)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    return _pdf_response(pdf, f"usuarios_{fecha}.pdf")


@router.get("/reportes/historial.pdf")
def reporte_historial_pdf(usuario: dict = Depends(requiere_admin),
                           desde: str = "", hasta: str = ""):
    try:
        fi = datetime.fromisoformat(desde) if desde else None
        ff = datetime.fromisoformat(hasta) if hasta else None
    except ValueError:
        fi, ff = None, None
    if fi and ff:
        prestamos = prestamo_service.historial_completo(fi, ff)
    else:
        prestamos = prestamo_service.historial_completo()
    pdf = reporte_service.reporte_historial(prestamos, fi, ff)
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    return _pdf_response(pdf, f"historial_{fecha}.pdf")
