"""Instancia única compartida de Jinja2Templates."""
import os
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _asset_version(rel_path: str) -> int:
    """Devuelve el mtime del archivo estático para usar como cache-buster."""
    full = os.path.join("app/static", rel_path.lstrip("/"))
    try:
        return int(os.path.getmtime(full))
    except OSError:
        return 0


# Disponible en todos los templates como {{ asset_v('css/style.css') }}
templates.env.globals["asset_v"] = _asset_version
