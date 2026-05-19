"""
JWT para sesiones web: el token se guarda en una cookie HTTP-only.
La cookie se llama 'prestamo_session' y expira junto con el token.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Cookie, Request
from fastapi.responses import RedirectResponse

load_dotenv()

SECRET_KEY      = os.getenv("JWT_SECRET_KEY", "dev_secret_cambia_en_produccion")
ALGORITHM       = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 8))
COOKIE_NAME     = "prestamo_session"


# ─── Generación y validación ──────────────────────────────────────────────────

def generar_token(usuario_id: int, nombre: str, correo: str, rol: str) -> str:
    payload = {
        "sub": str(usuario_id),
        "nombre": nombre,
        "correo": correo,
        "rol": rol,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=EXPIRATION_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def validar_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ─── Dependencias FastAPI ─────────────────────────────────────────────────────

def get_usuario_actual(request: Request) -> dict | None:
    """Lee el JWT de la cookie y retorna el payload, o None si no hay sesión."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return validar_token(token)


def requiere_login(request: Request) -> dict:
    """Dependencia: redirige a /login si no hay sesión activa."""
    payload = get_usuario_actual(request)
    if not payload:
        # FastAPI no soporta raise RedirectResponse en depends; usamos HTTPException
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No autenticado")
    return payload


def requiere_admin(request: Request) -> dict:
    """Dependencia: exige rol administrador."""
    payload = requiere_login(request)
    if payload.get("rol") != "administrador":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return payload


def requiere_cliente(request: Request) -> dict:
    """Dependencia: exige rol cliente."""
    payload = requiere_login(request)
    if payload.get("rol") != "cliente":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return payload


# ─── Respuestas con cookie ────────────────────────────────────────────────────

def set_cookie_response(response, token: str):
    """Añade la cookie JWT HTTP-only a una respuesta."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=EXPIRATION_HOURS * 3600,
    )
    return response


def delete_cookie_response(response):
    """Elimina la cookie de sesión (logout)."""
    response.delete_cookie(COOKIE_NAME)
    return response


# ─── Password hashing ────────────────────────────────────────────────────────

def hashear_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def verificar_password(password: str, hash_str: str) -> bool:
    return bcrypt.checkpw(password.encode(), hash_str.encode())
