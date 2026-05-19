"""Rutas de autenticación: login, logout, registro."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.jwt_handler import delete_cookie_response, get_usuario_actual, set_cookie_response
from app.services.auth_service import login, registrar_cliente
from app.templates_config import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def get_login(request: Request, msg: str = "", tipo: str = ""):
    if get_usuario_actual(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"msg": msg, "tipo": tipo})


@router.post("/login")
def post_login(request: Request, correo: str = Form(...), password: str = Form(...)):
    resultado = login(correo.strip(), password)
    if not resultado["exito"]:
        return templates.TemplateResponse(
            request, "login.html",
            {"msg": resultado["mensaje"], "tipo": "error"},
        )
    destino = "/admin/dashboard" if resultado["rol"] == "administrador" else "/cliente/productos"
    response = RedirectResponse(destino, status_code=302)
    set_cookie_response(response, resultado["token"])
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    delete_cookie_response(response)
    return response


@router.get("/register", response_class=HTMLResponse)
def get_register(request: Request, msg: str = "", tipo: str = ""):
    return templates.TemplateResponse(request, "register.html", {"msg": msg, "tipo": tipo})


@router.post("/register")
def post_register(request: Request,
                  nombre: str = Form(...), apellido: str = Form(...),
                  correo: str = Form(...), documento: str = Form(""),
                  password: str = Form(...), confirm: str = Form(...)):
    if len(password) < 6:
        return templates.TemplateResponse(
            request, "register.html",
            {"msg": "La contraseña debe tener al menos 6 caracteres.", "tipo": "error"},
        )
    if password != confirm:
        return templates.TemplateResponse(
            request, "register.html",
            {"msg": "Las contraseñas no coinciden.", "tipo": "error"},
        )
    res = registrar_cliente(nombre, apellido, correo.strip(), password, documento.strip() or None)
    if res["exito"]:
        return RedirectResponse("/login?msg=Cuenta+creada+exitosamente&tipo=success", status_code=302)
    return templates.TemplateResponse(
        request, "register.html", {"msg": res["mensaje"], "tipo": "error"}
    )
