from __future__ import annotations

import secrets
from datetime import datetime

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


def verificar_credenciales_estudiante(correo: str, password: str,
                                       usuario_id_esperado: int) -> dict:
    """Valida correo + contraseña y que correspondan al usuario dueño del préstamo."""
    correo = (correo or "").strip().lower()
    if not correo or not password:
        return {"exito": False, "mensaje": "Debe ingresar correo y contraseña del estudiante."}

    rows = ejecutar_query(
        "SELECT * FROM fn_obtener_usuario_login(%s)", (correo,)
    )
    if not rows:
        return {"exito": False, "mensaje": "El estudiante no está registrado."}

    u = rows[0]
    if u["usuario_id"] != usuario_id_esperado:
        return {"exito": False,
                "mensaje": "El correo ingresado no corresponde al estudiante del préstamo."}
    if not u["activo"]:
        return {"exito": False, "mensaje": "La cuenta del estudiante está desactivada."}
    if not verificar_password(password, u["password_hash"]):
        return {"exito": False, "mensaje": "Contraseña del estudiante incorrecta."}

    return {"exito": True, "correo": u["correo"],
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


def generar_codigo_barras_usuario() -> str:
    """Genera un código de barras único para un usuario.
    Patrón: USR-YYYYMMDD-XXXXXX (6 hex aleatorios).
    Reintenta hasta encontrar uno libre.
    """
    fecha = datetime.now().strftime("%Y%m%d")
    for _ in range(10):
        codigo = f"USR-{fecha}-{secrets.token_hex(3).upper()}"
        rows = ejecutar_query(
            "SELECT 1 FROM usuarios WHERE codigo_barras = %s", (codigo,)
        )
        if not rows:
            return codigo
    # Fallback poco probable: incluir microsegundos
    return f"USR-{fecha}-{secrets.token_hex(4).upper()}{datetime.now().microsecond}"


def registrar_usuario_admin(nombre: str, apellido: str, correo: str,
                             password: str, rol: str,
                             numero_documento: str | None = None,
                             codigo_barras: str | None = None) -> dict:
    correo_limpio = correo.strip().lower()
    # Validar que el código de barras no esté usado
    if codigo_barras:
        rows = ejecutar_query(
            "SELECT 1 FROM usuarios WHERE codigo_barras = %s", (codigo_barras,)
        )
        if rows:
            return {"exito": False, "usuario_id": None,
                    "mensaje": f"El código de barras '{codigo_barras}' ya está asignado a otro usuario."}

    pw_hash = hashear_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CALL sp_registrar_usuario(%s,%s,%s,%s,%s::tipo_rol,%s,NULL,NULL)",
                (nombre, apellido, correo_limpio, pw_hash, rol, numero_documento),
            )
            row = cur.fetchone()
            if not row or row["p_usuario_id"] <= 0:
                return {"exito": False, "usuario_id": None,
                        "mensaje": row["p_mensaje"] if row else "Error."}
            usuario_id = row["p_usuario_id"]
            mensaje    = row["p_mensaje"]
            if codigo_barras:
                cur.execute(
                    "UPDATE usuarios SET codigo_barras = %s WHERE id = %s",
                    (codigo_barras, usuario_id),
                )
    return {"exito": True, "usuario_id": usuario_id, "mensaje": mensaje}


def actualizar_usuario(usuario_id: int, nombre: str, apellido: str,
                        correo: str, documento: str | None,
                        codigo_barras: str | None, activo: bool,
                        password: str | None = None) -> dict:
    correo_limpio = (correo or "").strip().lower()
    # Validar correo único (excepto el propio usuario)
    rows = ejecutar_query(
        "SELECT 1 FROM usuarios WHERE correo = %s AND id != %s",
        (correo_limpio, usuario_id),
    )
    if rows:
        return {"exito": False,
                "mensaje": "El correo ya está registrado en otro usuario."}
    # Validar código de barras único (si se especifica)
    if codigo_barras:
        rows = ejecutar_query(
            "SELECT 1 FROM usuarios WHERE codigo_barras = %s AND id != %s",
            (codigo_barras, usuario_id),
        )
        if rows:
            return {"exito": False,
                    "mensaje": f"El código de barras '{codigo_barras}' ya está asignado a otro usuario."}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE usuarios
                   SET nombre=%s, apellido=%s, correo=%s,
                       numero_documento=%s, codigo_barras=%s, activo=%s
                   WHERE id=%s""",
                (nombre, apellido, correo_limpio, documento,
                 codigo_barras, activo, usuario_id),
            )
            if cur.rowcount == 0:
                return {"exito": False, "mensaje": "Usuario no encontrado."}
            if password:
                cur.execute(
                    "UPDATE usuarios SET password_hash = %s WHERE id = %s",
                    (hashear_password(password), usuario_id),
                )
    return {"exito": True, "mensaje": "Usuario actualizado correctamente."}
