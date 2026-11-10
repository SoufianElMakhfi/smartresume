"""PDF-Erzeugung mit Typst (Deckblatt → Anschreiben → Lebenslauf)."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from . import paths
from .profile import link_icon, profile_city

ROOT = paths.app_dir()
TEMPLATE = ROOT / "template.typ"
FONTS = ROOT / "fonts"
ICONS = ROOT / "icons"

MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
             "September", "Oktober", "November", "Dezember"]

LABELS = {
    "document_title": "Bewerbung",
    "application_as": "Bewerbung als",
    "about": "Über mich",
    "cv": "Lebenslauf",
    "experience": "Berufserfahrung",
    "education": "Ausbildung",
    "skills": "Fähigkeiten",
    "closing": "Mit freundlichen Grüßen",
}


class RenderError(RuntimeError):
    pass


def german_date(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.day}. {MONTHS_DE[d.month - 1]} {d.year}"


def _nbsp_units(s: str) -> str:
    """Kein Zeilenumbruch vor Einheiten (50 % / 1.000 €)."""
    return re.sub(r"(\d) (%|€|Std\.?|h\b)", "\\1\u00a0\\2", s or "")


def find_typst() -> str | None:
    exe = shutil.which("typst")
    if exe:
        return exe
    local = os.environ.get("LOCALAPPDATA", "")
    for c in (
        os.environ.get("TYPST_BIN", ""),
        os.path.join(local, r"Microsoft\WinGet\Packages\Typst.Typst_Microsoft.Winget.Source_8wekyb3d8bbwe"
                            r"\typst-x86_64-pc-windows-msvc\typst.exe"),
        r"C:\Program Files\typst\typst.exe",
    ):
        if c and os.path.exists(c):
            return c
    return None


def prepare_photo(raw: bytes, size: int = 800) -> bytes:
    """Quadratisch zuschneiden (Mitte, leicht nach oben für Gesichter), verkleinern, als JPEG."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, min(h - side, int((h - side) * 0.3)))  # Porträts: eher oberen Bereich behalten
    img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def prepare_signature(raw: bytes) -> bytes:
    """Weißen Hintergrund transparent machen und auf Inhalt zuschneiden."""
    from PIL import Image, ImageChops

    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    r, g, b, a = img.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)       # min(r, g, b) je Pixel
    keep = darkest.point(lambda v: 255 if v <= 225 else 0)       # fast-weiß → transparent
    img.putalpha(ImageChops.multiply(a, keep))
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def build_render_data(structured: dict, profile: dict, *, accent: str, font: str,
                      show_photo: bool, show_links: bool, has_photo: bool, has_signature: bool) -> dict:
    pers = profile["personal"]
    cl = structured.get("cover_letter", {})
    contact = [x for x in (f"{pers['street']}, {pers['zip_city']}".strip(", "), pers["phone"], pers["email"]) if x]
    recipient = [x for x in (cl.get("contact_person", ""), cl.get("department", ""),
                             cl.get("street", ""), cl.get("city", "")) if x]
    # "Frau Weber" nicht doppelt, falls Abteilung = Ansprechpartner
    recipient = list(dict.fromkeys(recipient))
    links = [{"label": l["label"], "url": l["url"], "icon": link_icon(l["label"], l["url"])}
             for l in pers["links"]]
    portfolio = next((l["url"] for l in pers["links"] if l["label"].lower() in ("portfolio", "website")), "")
    city = profile_city(profile)
    job_title = cl.get("job_title", "")
    subject = cl.get("subject") or (f"Bewerbung als {job_title}" if job_title else "Bewerbung")
    paragraphs = [_nbsp_units(cl.get(p, "")) for p in ("p1", "p2", "p3", "p4") if cl.get(p, "").strip()]

    def skill_items(s):
        items = s.get("items", "")
        return ", ".join(items) if isinstance(items, list) else str(items)

    return {
        "accent": accent,
        "font": font,
        "labels": LABELS,
        "person": {
            "name": pers["name"],
            "contact_line": "  ·  ".join(contact),
            "sender_line": " · ".join(x for x in (pers["name"], *contact) if x),
        },
        "links": links,
        "show_links": bool(show_links and links),
        "portfolio_url": portfolio if show_links else "",
        "photo": "photo.jpg" if (show_photo and has_photo) else "",
        "signature": "signature.png" if has_signature else "",
        "date_line": f"{city}, {german_date()}" if city else german_date(),
        "job_title": job_title,
        "summary": _nbsp_units(structured.get("summary", "")),
        "experience": [{"role": j.get("role", ""), "company": j.get("company", ""), "dates": j.get("dates", ""),
                        "location": j.get("location", ""),
                        "bullets": [_nbsp_units(b) for b in j.get("bullets", []) if b.strip()]}
                       for j in structured.get("experience", [])],
        "education": [{"institution": e.get("institution", ""), "degree": e.get("degree", ""),
                       "dates": e.get("dates", ""), "location": e.get("location", ""),
                       "detail": e.get("detail", "")} for e in structured.get("education", [])],
        "skills": [{"category": s.get("category", ""), "items": skill_items(s)}
                   for s in structured.get("skills", []) if skill_items(s)],
        "cover_letter": {
            "company": cl.get("company", ""),
            "recipient_lines": recipient,
            "subject": subject,
            "salutation": cl.get("salutation") or "Sehr geehrte Damen und Herren,",
            "paragraphs": paragraphs,
        },
    }


def render_pdf(structured: dict, profile: dict, *, photo: bytes | None = None, signature: bytes | None = None,
               accent: str = "#0F5F6E", font: str = "Lexend", show_photo: bool = True,
               show_links: bool = True) -> bytes:
    data = build_render_data(structured, profile, accent=accent, font=font, show_photo=show_photo,
                             show_links=show_links, has_photo=bool(photo), has_signature=bool(signature))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copy(TEMPLATE, tmp / "main.typ")
        (tmp / "icons").mkdir()
        for svg in ICONS.glob("*.svg"):  # Icons in der Akzentfarbe einfärben
            (tmp / "icons" / svg.name).write_text(
                re.sub(r"#0F5F6E", accent, svg.read_text(encoding="utf-8"), flags=re.IGNORECASE), encoding="utf-8")
        (tmp / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if data["photo"]:
            (tmp / "photo.jpg").write_bytes(photo)
        if data["signature"]:
            (tmp / "signature.png").write_bytes(signature)
        out = tmp / "out.pdf"
        exe = find_typst()
        if exe:
            r = subprocess.run([exe, "compile", "--font-path", str(FONTS), "--root", str(tmp),
                                str(tmp / "main.typ"), str(out)], capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                raise RenderError(f"Typst-Fehler:\n{r.stderr[-1500:]}")
            return out.read_bytes()
        try:
            import typst  # Python-Paket als Fallback (z.B. Streamlit Cloud)
        except ImportError:
            raise RenderError("Typst nicht gefunden. Installieren: winget install --id Typst.Typst "
                              "oder pip install typst")
        try:
            return typst.compile(str(tmp / "main.typ"), font_paths=[str(FONTS)], root=str(tmp))
        except Exception as e:  # noqa: BLE001
            raise RenderError(f"Typst-Fehler: {e}")


def count_pages(pdf: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf)).pages)


def pdf_text(pdf: bytes) -> list[str]:
    from pypdf import PdfReader
    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages]
