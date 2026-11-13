"""Anlagen (Zeugnisse, Zertifikate, Nachweise): beim Hochladen in PDF umwandeln, beim Bewerben anhängen.

Alles bleibt lokal. Fotos/Scans (JPG/PNG) werden auf eine A4-Seite gesetzt, damit die Bewerbungsmappe
einheitlich aussieht und jedes Bewerbersystem sie öffnen kann.
"""
from __future__ import annotations

import io
from pathlib import Path

TYPES = ["pdf", "jpg", "jpeg", "png"]
MAX_MB = 10
_A4_PX = (1240, 1754)      # A4 bei 150 dpi
_MARGIN = 60


class AttachmentError(ValueError):
    pass


def title_from_filename(filename: str) -> str:
    return Path(filename or "Anlage").stem.replace("_", " ").strip() or "Anlage"


def to_pdf(filename: str, data: bytes) -> bytes:
    """Datei → PDF-Bytes. PDFs werden geprüft und unverändert übernommen, Bilder auf A4 gesetzt."""
    if len(data) > MAX_MB * 1024 * 1024:
        raise AttachmentError(f"„{filename}“ ist größer als {MAX_MB} MB.")
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise AttachmentError(f"„{filename}“ ist passwortgeschützt – bitte eine ungeschützte PDF hochladen.")
            if not reader.pages:
                raise AttachmentError(f"„{filename}“ enthält keine Seiten.")
        except AttachmentError:
            raise
        except Exception as e:  # noqa: BLE001 – pypdf wirft diverse Formatfehler
            raise AttachmentError(f"„{filename}“ konnte nicht gelesen werden ({e}).") from None
        return data
    from PIL import Image, ImageOps
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:  # noqa: BLE001
        raise AttachmentError(f"„{filename}“ ist weder PDF noch ein lesbares Bild (JPG/PNG).") from None
    page = Image.new("RGB", _A4_PX, "white")
    box = (_A4_PX[0] - 2 * _MARGIN, _A4_PX[1] - 2 * _MARGIN)
    img.thumbnail(box, Image.LANCZOS)          # verkleinert nur, vergrößert nie
    page.paste(img, ((_A4_PX[0] - img.width) // 2, _MARGIN))
    out = io.BytesIO()
    page.save(out, "PDF", resolution=150)
    return out.getvalue()


def merge(pdfs: list[bytes]) -> bytes:
    """Mehrere PDFs zu einer Datei (Reihenfolge bleibt)."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for pdf in pdfs:
        w.append(PdfReader(io.BytesIO(pdf)))
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def page_count(pdf: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf)).pages)
