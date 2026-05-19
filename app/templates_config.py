"""Instancia única compartida de Jinja2Templates."""
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/templates")
