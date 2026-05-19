"""
Módulo de conexión a PostgreSQL usando psycopg (v3).
Dentro de Docker, la app conecta al servicio 'postgres' por nombre de host.
"""
from __future__ import annotations

import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

_DB_CONNINFO = (
    f"host={os.getenv('DB_HOST', 'postgres')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'prestamos_umb')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', 'postgres')}"
)


def get_conn() -> psycopg.Connection:
    """Abre una conexión con row_factory=dict_row para obtener filas como dicts."""
    return psycopg.connect(_DB_CONNINFO, row_factory=dict_row)


def ejecutar_query(sql: str, params: tuple = None) -> list[dict]:
    """Ejecuta un SELECT y retorna lista de dicts."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def ejecutar_comando(sql: str, params: tuple = None) -> int:
    """Ejecuta INSERT/UPDATE/DELETE y retorna filas afectadas."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def verificar_conexion() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
