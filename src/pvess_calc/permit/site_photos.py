"""PV-7 site photos sheet for reference-style permit packages."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from ..calc.engine import CalculationResult
from ._textfit import fit


REQUIRED_PHOTOS: tuple[tuple[str, str], ...] = (
    ("front_elevation", "Front elevation"),
    ("roof", "Roof / array area"),
    ("meter", "Utility meter"),
    ("main_panel", "Main service panel"),
    ("sub_panel", "Sub-panel / load center"),
    ("equipment_location", "Proposed equipment location"),
)


def render_site_photos(result: CalculationResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=landscape(letter))
    W, H = landscape(letter)

    c.setLineWidth(1.0)
    c.rect(0.35 * inch, 0.35 * inch, W - 0.70 * inch, H - 0.70 * inch)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(W / 2, H - 0.72 * inch, "PV-7 · SITE PHOTOS")
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(
        W / 2, H - 0.94 * inch,
        result.inputs.project.site_address or result.inputs.project.location,
    )

    supplied = {p.kind: p for p in result.inputs.project.site_photos}
    cells = REQUIRED_PHOTOS
    x0 = 0.55 * inch
    y_top = H - 1.18 * inch
    gap = 0.16 * inch
    cell_w = (W - 1.10 * inch - 2 * gap) / 3
    cell_h = (y_top - 0.55 * inch - gap) / 2

    for idx, (kind, default_caption) in enumerate(cells):
        col = idx % 3
        row = idx // 3
        x = x0 + col * (cell_w + gap)
        y = y_top - (row + 1) * cell_h - row * gap
        photo = supplied.get(kind)
        caption = (photo.caption if photo and photo.caption else default_caption)
        path = _photo_path(result, photo.path) if photo and photo.path else None
        _draw_photo_cell(c, x, y, cell_w, cell_h, caption, path)

    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(colors.HexColor("#6B7280"))
    c.drawRightString(
        W - 0.42 * inch, 0.42 * inch,
        "Missing photos are placeholders for installer/site-survey completion.",
    )
    c.save()


def _photo_path(result: CalculationResult, raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    return Path.cwd() / "projects" / result.inputs.project.id / p


def _draw_photo_cell(
    c, x: float, y: float, w: float, h: float, caption: str, path: Path | None,
) -> None:
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.55)
    c.rect(x, y, w, h)
    caption_h = 0.24 * inch
    image_y = y + caption_h
    image_h = h - caption_h

    if path and path.exists():
        try:
            img = ImageReader(str(path))
            c.drawImage(
                img, x + 0.06 * inch, image_y + 0.06 * inch,
                width=w - 0.12 * inch, height=image_h - 0.12 * inch,
                preserveAspectRatio=True, anchor="c",
            )
        except Exception:
            _placeholder(c, x, image_y, w, image_h, "IMAGE LOAD FAILED")
    else:
        _placeholder(c, x, image_y, w, image_h, "PHOTO REQUIRED")

    c.setFillColor(colors.white)
    c.rect(x, y, w, caption_h, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(
        x + 0.08 * inch,
        y + 0.08 * inch,
        fit(caption, "Helvetica-Bold", 7.5, w - 0.16 * inch),
    )


def _placeholder(c, x: float, y: float, w: float, h: float, text: str) -> None:
    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.rect(x + 0.06 * inch, y + 0.06 * inch,
           w - 0.12 * inch, h - 0.12 * inch, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x + w / 2, y + h / 2, text)
    c.setFillColor(colors.black)
