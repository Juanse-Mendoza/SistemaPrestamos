"""Generación de reportes PDF con reportlab."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)


NAVY    = colors.HexColor("#1e2845")
BG_ALT  = colors.HexColor("#f5f7fe")
BORDER  = colors.HexColor("#cbd5e1")
TEXT_2  = colors.HexColor("#6b7a99")


def _estilos():
    base = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloReporte", parent=base["Title"],
        fontSize=18, textColor=NAVY, spaceAfter=4, alignment=0,
    )
    subtitulo = ParagraphStyle(
        "Subtitulo", parent=base["Normal"],
        fontSize=10, textColor=TEXT_2, spaceAfter=2,
    )
    return titulo, subtitulo, base["Normal"]


# Estilos reutilizables para celdas (texto largo con wrap)
_celda = ParagraphStyle(
    "Celda", fontName="Helvetica", fontSize=8,
    leading=10, textColor=colors.HexColor("#1e2845"),
    wordWrap="LTR",
)
_celda_centro = ParagraphStyle(
    "CeldaCentro", parent=_celda, alignment=1,
)
_celda_mono = ParagraphStyle(
    "CeldaMono", parent=_celda, fontName="Courier", fontSize=7.5,
)
_header = ParagraphStyle(
    "Header", fontName="Helvetica-Bold", fontSize=9,
    leading=11, textColor=colors.white, alignment=1,
)


def _P(texto, estilo=_celda) -> Paragraph:
    """Crea un Paragraph escapando caracteres XML mínimos."""
    if texto is None or texto == "":
        return Paragraph("—", estilo)
    s = str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(s, estilo)


def _tabla_estilo() -> TableStyle:
    return TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), NAVY),
        ("GRID",         (0, 0), (-1, -1), 0.4, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_ALT]),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ])


def _construir_pdf(titulo: str, headers: list[str], rows: list[list],
                    subtitulo: str = "", apaisado: bool = True,
                    col_widths: list[float] | None = None) -> bytes:
    """Crea un PDF con encabezado y una tabla. `rows` contiene Paragraph o str.
    Si los anchos suman más que el área disponible, reportlab los ajusta."""
    buf = BytesIO()
    pagesize = landscape(A4) if apaisado else A4
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm,  bottomMargin=1.5 * cm,
        title=titulo, author="PrestaUni",
    )

    st_titulo, st_sub, st_norm = _estilos()
    elems = []
    elems.append(Paragraph("<b>PrestaUni — Universidad Manuela Beltrán</b>", st_sub))
    elems.append(Paragraph(titulo, st_titulo))
    if subtitulo:
        elems.append(Paragraph(subtitulo, st_sub))
    elems.append(Paragraph(
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} · Total registros: {len(rows)}",
        st_sub,
    ))
    elems.append(Spacer(1, 0.4 * cm))

    if rows:
        # Encabezado con Paragraph para wrap también
        header_row = [Paragraph(h, _header) for h in headers]
        data = [header_row] + rows
        tabla = Table(data, repeatRows=1, colWidths=col_widths)
        tabla.setStyle(_tabla_estilo())
        elems.append(tabla)
    else:
        elems.append(Paragraph(
            "<i>No hay registros que mostrar en este reporte.</i>", st_norm
        ))

    def _pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(TEXT_2)
        canvas.drawString(1.2 * cm, 0.8 * cm,
                          f"PrestaUni · Reporte generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        canvas.drawRightString(pagesize[0] - 1.2 * cm, 0.8 * cm,
                               f"Página {doc_.page}")
        canvas.restoreState()

    doc.build(elems, onFirstPage=_pie, onLaterPages=_pie)
    return buf.getvalue()


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    s = str(v)
    return s if s else "—"


def _legible_minutos(minutos: int | None) -> str:
    if not minutos:
        return "Sin límite"
    if minutos % 1440 == 0:
        return f"{minutos // 1440} día(s)"
    if minutos % 60 == 0:
        return f"{minutos // 60} hora(s)"
    return f"{minutos} min"


# Área útil en apaisado A4 con márgenes de 1.2cm a cada lado: ~27.7cm
# Total disponible aprox: 27.7 cm — repartir las columnas para sumar <= 27.7

# ── Reporte: Productos / Inventario ──────────────────────────────────────────

def reporte_productos(articulos: list[dict]) -> bytes:
    headers = [
        "Código\ninterno", "Código de\nbarras", "Nombre del artículo",
        "Categoría", "Estado", "Disp.", "Total",
        "Tiempo\nmáx.", "Ubicación",
    ]
    rows = []
    for a in articulos:
        rows.append([
            _P(a.get("codigo_interno"), _celda_mono),
            _P(a.get("codigo_barras"), _celda_mono),
            _P(a.get("articulo")),
            _P(a.get("categoria")),
            _P((a.get("estado") or "").upper(), _celda_centro),
            _P(a.get("stock_disponible") or 0, _celda_centro),
            _P(a.get("stock_total") or 0, _celda_centro),
            _P(_legible_minutos(a.get("tiempo_maximo_minutos")), _celda_centro),
            _P(a.get("ubicacion")),
        ])
    # Total: 2.2 + 2.6 + 6.5 + 3.0 + 2.0 + 1.3 + 1.3 + 2.4 + 4.4 = 25.7 cm
    widths = [2.2*cm, 2.6*cm, 6.5*cm, 3.0*cm, 2.0*cm, 1.3*cm, 1.3*cm, 2.4*cm, 4.4*cm]
    return _construir_pdf(
        "Inventario de artículos", headers, rows,
        subtitulo=f"Total artículos: {len(articulos)}",
        col_widths=widths,
    )


# ── Reporte: Usuarios ────────────────────────────────────────────────────────

def reporte_usuarios(usuarios: list[dict]) -> bytes:
    headers = [
        "Nombre completo", "Correo", "Documento", "Código de\nbarras",
        "Rol", "Activo", "Total\npréstamos", "Activos", "Fecha de\nregistro",
    ]
    rows = []
    for u in usuarios:
        rows.append([
            _P(u.get("nombre_completo")),
            _P(u.get("correo"), _celda_mono),
            _P(u.get("numero_documento"), _celda_centro),
            _P(u.get("codigo_barras"), _celda_mono),
            _P((u.get("rol") or "").capitalize(), _celda_centro),
            _P("Sí" if u.get("activo") else "No", _celda_centro),
            _P(u.get("total_prestamos") or 0, _celda_centro),
            _P(u.get("prestamos_activos") or 0, _celda_centro),
            _P(_fmt(u.get("fecha_creacion")), _celda_centro),
        ])
    # Total: 4.8 + 5.0 + 2.4 + 3.4 + 1.8 + 1.3 + 1.8 + 1.6 + 2.6 = 24.7 cm
    widths = [4.8*cm, 5.0*cm, 2.4*cm, 3.4*cm, 1.8*cm, 1.3*cm, 1.8*cm, 1.6*cm, 2.6*cm]
    return _construir_pdf(
        "Usuarios del sistema", headers, rows,
        subtitulo=f"Total usuarios: {len(usuarios)}",
        col_widths=widths,
    )


# ── Reporte: Historial de préstamos ──────────────────────────────────────────

def reporte_historial(prestamos: list[dict],
                       desde: datetime | None, hasta: datetime | None) -> bytes:
    headers = [
        "Código", "Estudiante", "Artículo", "Categoría",
        "Estado", "Fecha\npréstamo", "Devolución\nesperada",
        "Devolución\nreal", "Cumplimiento",
    ]
    rows = []
    for p in prestamos:
        rows.append([
            _P(p.get("codigo_prestamo"), _celda_mono),
            _P(p.get("usuario_nombre")),
            _P(p.get("articulo")),
            _P(p.get("categoria")),
            _P((p.get("estado_prestamo") or "").upper(), _celda_centro),
            _P(_fmt(p.get("fecha_prestamo")), _celda_centro),
            _P(_fmt(p.get("fecha_devolucion_esperada")), _celda_centro),
            _P(_fmt(p.get("fecha_devolucion_real")), _celda_centro),
            _P(p.get("cumplimiento"), _celda_centro),
        ])
    if desde and hasta:
        sub = f"Periodo: {desde.strftime('%Y-%m-%d')} hasta {hasta.strftime('%Y-%m-%d')}"
    elif desde:
        sub = f"Desde: {desde.strftime('%Y-%m-%d')}"
    elif hasta:
        sub = f"Hasta: {hasta.strftime('%Y-%m-%d')}"
    else:
        sub = "Todos los préstamos registrados"
    # Total: 2.6 + 3.8 + 4.4 + 2.8 + 1.8 + 2.4 + 2.4 + 2.4 + 2.6 = 25.2 cm
    widths = [2.6*cm, 3.8*cm, 4.4*cm, 2.8*cm, 1.8*cm, 2.4*cm, 2.4*cm, 2.4*cm, 2.6*cm]
    return _construir_pdf(
        "Historial de préstamos", headers, rows,
        subtitulo=sub, col_widths=widths,
    )
