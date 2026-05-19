from __future__ import annotations

from app.auth.jwt_handler import generar_token, hashear_password, verificar_password
from app.database.connection import ejecutar_query, get_conn


def login(correo: str, password: str) -> dict:
    rows = ejecutar_query(
        "SELECT * FROM fn_obtener_usuario_login(%s)", (correo.lower(),)
    )
    if not rows:
        return {"exito": False, "mensaje": "Correo o contraseña incorrectos."}
    u = rows[0]
    if not u["activo"]:
        return {"exito": False, "mensaje": "Cuenta desactivada. Contacte al administrador."}
    if not verificar_password(password, u["password_hash"]):
        return {"exito": False, "mensaje": "Correo o contraseña incorrectos."}
    token = generar_token(
        usuario_id=u["usuario_id"],
        nombre=f"{u['nombre']} {u['apellido']}",
        correo=u["correo"],
        rol=u["rol_nombre"],
    )
    return {"exito": True, "token": token, "rol": u["rol_nombre"],
            "nombre": f"{u['nombre']} {u['apellido']}"}


def registrar_cliente(nombre: str, apellido: str, correo: str,
                       password: str, numero_documento: str | None = None) -> dict:
    pw_hash = hashear_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_usuario(%s,%s,%s,%s,%s::tipo_rol,%s,NULL,NULL)",
                (nombre, apellido, correo, pw_hash, "cliente", numero_documento),
            )
            row = cur.fetchone()
    if row and row["p_usuario_id"] > 0:
        return {"exito": True, "mensaje": row["p_mensaje"]}
    return {"exito": False, "mensaje": row["p_mensaje"] if row else "Error desconocido."}


def registrar_usuario_admin(nombre: str, apellido: str, correo: str,
                             password: str, rol: str,
                             numero_documento: str | None = None) -> dict:
    pw_hash = hashear_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_usuario(%s,%s,%s,%s,%s::tipo_rol,%s,NULL,NULL)",
                (nombre, apellido, correo, pw_hash, rol, numero_documento),
            )
            row = cur.fetchone()
    if row and row["p_usuario_id"] > 0:
        return {"exito": True, "usuario_id": row["p_usuario_id"], "mensaje": row["p_mensaje"]}
    return {"exito": False, "usuario_id": None, "mensaje": row["p_mensaje"] if row else "Error."}
