"""Punto de entrada FastAPI — PrestaUni."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes.auth_routes import router as auth_router
from app.routes.admin_routes import router as admin_router
from app.routes.cliente_routes import router as cliente_router
from app.templates_config import templates

app = FastAPI(title="PrestaUni", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(admin_router, prefix="/admin")
app.include_router(cliente_router, prefix="/cliente")


@app.get("/")
def raiz(request: Request):
    from app.auth.jwt_handler import get_usuario_actual
    u = get_usuario_actual(request)
    if not u:
        return RedirectResponse("/login", status_code=302)
    if u["rol"] == "administrador":
        return RedirectResponse("/admin/dashboard", status_code=302)
    return RedirectResponse("/cliente/productos", status_code=302)


@app.exception_handler(401)
async def no_autenticado(request: Request, exc):
    return RedirectResponse("/login", status_code=302)


@app.exception_handler(403)
async def sin_permiso(request: Request, exc):
    return templates.TemplateResponse(request, "403.html", {}, status_code=403)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
