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


@router.get("/api/buscar-estudiante/{documento}")
def api_buscar_estudiante(documento: str, usuario: dict = Depends(requiere_admin)):
    """Busca un estudiante activo por numero_documento O codigo_barras del carnet."""
    from app.database.connection import ejecutar_query
    rows = ejecutar_query(
        """SELECT nombre, apellido, correo FROM usuarios
           WHERE (numero_documento = %s OR codigo_barras = %s) AND activo = TRUE
           LIMIT 1""",
        (documento, documento)
    )
    if rows:
        u = rows[0]
        return JSONResponse({"encontrado": True,
                             "nombre": f"{u['nombre']} {u['apellido']}",
                             "correo": u["correo"]})
    return JSONResponse({"encontrado": False})


@router.get("/api/generar-codigo-usuario")
def api_generar_codigo_usuario(usuario: dict = Depends(requiere_admin)):
    """Genera un código de barras único para un carnet de usuario."""
    import uuid
    from app.database.connection import ejecutar_query
    for _ in range(10):
        code = f"USR-{uuid.uuid4().hex[:8].upper()}"
        if not ejecutar_query("SELECT 1 FROM usuarios WHERE codigo_barras=%s", (code,)):
            return JSONResponse({"codigo": code})
    return JSONResponse({"codigo": None})


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
    from app.database.connection import ejecutar_query
    solicitudes_count = {"total": ejecutar_query(
        "SELECT COUNT(*) AS c FROM prestamos WHERE estado='pendiente'"
    )[0]["c"]}
    multas_count = ejecutar_query(
        "SELECT COUNT(*) AS c FROM prestamos WHERE estado='vencido' AND (multa_pagada=FALSE OR multa_pagada IS NULL)"
    )[0]["c"]
    return templates.TemplateResponse(request, "admin/usuarios.html", _ctx(
        usuario,
        usuarios=prestamo_service.listar_usuarios(),
        solicitudes_count=solicitudes_count,
        multas_count=multas_count,
        msg=msg, tipo=tipo,
    ))


@router.post("/usuarios/nuevo")
def nuevo_usuario(usuario: dict = Depends(requiere_admin),
                  nombre: str = Form(...), apellido: str = Form(...),
                  correo: str = Form(...), documento: str = Form(""),
                  codigo_barras: str = Form(""),
                  password: str = Form(...), rol: str = Form(...)):
    res = registrar_usuario_admin(nombre, apellido, correo.strip(), password, rol,
                                   documento.strip() or None)
    if res["exito"] and codigo_barras.strip():
        from app.database.connection import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE usuarios SET codigo_barras=%s WHERE id=%s",
                            (codigo_barras.strip(), res["usuario_id"]))
    tipo = "success" if res["exito"] else "error"
    return RedirectResponse(f"/admin/usuarios?msg={res['mensaje']}&tipo={tipo}", status_code=302)


@router.post("/usuarios/{usuario_id}/editar")
def editar_usuario(usuario_id: int, usuario: dict = Depends(requiere_admin),
                   nombre: str = Form(...), apellido: str = Form(...),
                   correo: str = Form(...), documento: str = Form(""),
                   codigo_barras: str = Form(""), password: str = Form(""),
                   activo: str = Form("")):
    from app.database.connection import get_conn
    from app.auth.jwt_handler import hashear_password
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE usuarios
                SET nombre=%s, apellido=%s, correo=LOWER(%s),
                    numero_documento=%s, codigo_barras=%s,
                    activo=%s, fecha_actualizacion=NOW()
                WHERE id=%s
            """, (nombre.strip(), apellido.strip(), correo.strip(),
                  documento.strip() or None, codigo_barras.strip() or None,
                  activo == "on", usuario_id))
            if password.strip():
                cur.execute("UPDATE usuarios SET password_hash=%s WHERE id=%s",
                            (hashear_password(password.strip()), usuario_id))
    return RedirectResponse("/admin/usuarios?msg=Usuario+actualizado+correctamente&tipo=success",
                            status_code=302)


# ─── Solicitudes ──────────────────────────────────────────────────────────────

@router.get("/solicitudes", response_class=HTMLResponse)
def solicitudes(request: Request, usuario: dict = Depends(requiere_admin),
                msg: str = "", tipo: str = ""):
    from app.database.connection import ejecutar_query
    pendientes = ejecutar_query("""
        SELECT p.id AS prestamo_id, p.codigo_prestamo,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo,
               a.nombre AS articulo,
               p.fecha_prestamo, p.fecha_devolucion_esperada
        FROM prestamos p
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN articulos a ON a.id = p.articulo_id
        WHERE p.estado = 'pendiente'
        ORDER BY p.fecha_prestamo DESC
    """)
    disputas = ejecutar_query("""
        SELECT d.id AS devolucion_id, p.codigo_prestamo,
               u.nombre || ' ' || u.apellido AS usuario_nombre,
               u.correo AS usuario_correo,
               a.nombre AS articulo,
               d.estado_articulo_recibido,
               d.fecha_devolucion,
               p.motivo_rechazo
        FROM devoluciones d
        JOIN prestamos p ON p.id = d.prestamo_id
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN articulos a ON a.id = p.articulo_id
        WHERE d.estado_articulo_recibido IN ('mantenimiento', 'baja')
          AND p.estado = 'devuelto'
        ORDER BY d.fecha_devolucion DESC
        LIMIT 50
    """)
    multas_count = ejecutar_query("""
        SELECT COUNT(*) AS total FROM prestamos
        WHERE estado = 'vencido' AND (multa_pagada = FALSE OR multa_pagada IS NULL)
    """)[0]["total"]
    solicitudes_count = {"total": len(pendientes)}
    return templates.TemplateResponse(request, "admin/solicitudes.html", {
        "usuario": usuario,
        "pendientes": pendientes,
        "disputas": disputas,
        "solicitudes_count": solicitudes_count,
        "multas_count": multas_count,
        "msg": msg, "tipo": tipo,
    })


@router.post("/solicitudes/{prestamo_id}/cancelar")
def cancelar_solicitud(prestamo_id: int, usuario: dict = Depends(requiere_admin),
                       motivo: str = Form("")):
    from app.database.connection import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CALL sp_cancelar_prestamo_pendiente(%s,%s,%s,NULL)",
                        (prestamo_id, int(usuario["sub"]), motivo or "Cancelado por administrador"))
            row = cur.fetchone()
    msg = row["p_mensaje"] if row else "Procesado."
    return RedirectResponse(f"/admin/solicitudes?msg={msg}&tipo=success", status_code=302)


# ─── Multas ───────────────────────────────────────────────────────────────────

@router.get("/multas", response_class=HTMLResponse)
def multas(request: Request, usuario: dict = Depends(requiere_admin),
           msg: str = "", tipo: str = ""):
    from app.database.connection import ejecutar_query
    multas_data = ejecutar_query("""
        SELECT
            p.id AS prestamo_id,
            p.codigo_prestamo,
            p.estado AS estado_prestamo,
            u.nombre || ' ' || u.apellido AS usuario_nombre,
            u.correo AS usuario_correo,
            u.numero_documento,
            a.nombre AS articulo,
            p.fecha_devolucion_esperada,
            COALESCE(a.multa_por_hora_cop, 1000) AS multa_tasa_hora,
            EXTRACT(EPOCH FROM (NOW() - p.fecha_devolucion_esperada)) / 3600 AS multa_horas_raw,
            COALESCE(p.multa_monto_pagado, 0) AS multa_pagado,
            COALESCE(p.multa_pagada, FALSE) AS multa_pagada_bool
        FROM prestamos p
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN articulos a ON a.id = p.articulo_id
        WHERE p.estado IN ('vencido', 'devuelto')
          AND p.fecha_devolucion_esperada < NOW()
          AND (p.multa_pagada = FALSE OR p.multa_pagada IS NULL)
        ORDER BY p.fecha_devolucion_esperada ASC
    """)
    multas_lista = []
    for m in multas_data:
        horas  = max(0, round(float(m.get("multa_horas_raw") or 0), 1))
        tasa   = float(m.get("multa_tasa_hora") or 1000)
        monto  = round(horas * tasa, 0)
        pagado = float(m.get("multa_pagado") or 0)
        saldo  = max(0, monto - pagado)
        multas_lista.append({
            **m,
            "aun_activo":              m.get("estado_prestamo") == "vencido",
            "multa_horas":             horas,
            "multa_monto":             monto,
            "multa_pagado":            pagado,
            "multa_saldo":             saldo,
            "multa_tasa_hora_formato": f"${tasa:,.0f}",
            "multa_monto_formato":     f"${monto:,.0f}",
            "multa_pagado_formato":    f"${pagado:,.0f}",
            "multa_saldo_formato":     f"${saldo:,.0f}",
        })

    solicitudes_count = {"total": ejecutar_query(
        "SELECT COUNT(*) AS c FROM prestamos WHERE estado='pendiente'"
    )[0]["c"]}
    return templates.TemplateResponse(request, "admin/multas.html", {
        "usuario": usuario,
        "multas": multas_lista,
        "solicitudes_count": solicitudes_count,
        "msg": msg, "tipo": tipo,
    })


@router.post("/multas/{prestamo_id}/pagar")
def registrar_pago_multa(prestamo_id: int, usuario: dict = Depends(requiere_admin),
                          monto: float = Form(...),
                          observaciones: str = Form("")):
    from app.database.connection import get_conn, ejecutar_query
    rows = ejecutar_query("""
        SELECT p.multa_monto_pagado,
               p.fecha_devolucion_esperada,
               COALESCE(a.multa_por_hora_cop, 1000) AS tasa
        FROM prestamos p
        JOIN articulos a ON a.id = p.articulo_id
        WHERE p.id = %s
    """, (prestamo_id,))
    if not rows:
        return RedirectResponse("/admin/multas?msg=Prestamo+no+encontrado&tipo=error", status_code=302)
    row = rows[0]
    ya_pagado   = float(row.get("multa_monto_pagado") or 0)
    horas       = max(0, (datetime.now() - row["fecha_devolucion_esperada"]).total_seconds() / 3600)
    monto_total = round(horas * float(row.get("tasa") or 1000), 0)
    nuevo_pagado = ya_pagado + monto
    es_saldado   = nuevo_pagado >= monto_total
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE prestamos
                SET multa_monto_pagado    = %s,
                    multa_fecha_pago      = NOW(),
                    multa_admin_recibe_id = %s,
                    multa_observaciones   = %s,
                    multa_pagada          = %s
                WHERE id = %s
            """, (nuevo_pagado, int(usuario["sub"]), observaciones or None, es_saldado, prestamo_id))
    msg = "Multa+saldada+completamente" if es_saldado else "Abono+registrado+correctamente"
    return RedirectResponse(f"/admin/multas?msg={msg}&tipo=success", status_code=302)


# ─── Reportes PDF ─────────────────────────────────────────────────────────────

@router.get("/reportes/productos")
def reporte_productos(usuario: dict = Depends(requiere_admin)):
    from app.services.reporte_service import reporte_productos as gen_pdf
    articulos = articulo_service.listar_articulos()
    pdf = gen_pdf(articulos)
    from fastapi.responses import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=inventario.pdf"})


@router.get("/reportes/usuarios")
def reporte_usuarios_pdf(usuario: dict = Depends(requiere_admin)):
    from app.services.reporte_service import reporte_usuarios as gen_pdf
    from app.database.connection import ejecutar_query
    usuarios = ejecutar_query("SELECT * FROM v_usuarios")
    pdf = gen_pdf(usuarios)
    from fastapi.responses import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=usuarios.pdf"})


@router.get("/reportes/historial")
def reporte_historial_pdf(usuario: dict = Depends(requiere_admin),
                           desde: str = "", hasta: str = ""):
    from app.services.reporte_service import reporte_historial as gen_pdf
    from datetime import datetime
    fi = datetime.fromisoformat(desde) if desde else None
    ff = datetime.fromisoformat(hasta) if hasta else None
    prestamos = prestamo_service.historial_completo(fi, ff)
    pdf = gen_pdf(prestamos, fi, ff)
    from fastapi.responses import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=historial_prestamos.pdf"})
