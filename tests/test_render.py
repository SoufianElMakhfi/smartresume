import io
import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

from smartresume import generate, render
from smartresume.profile import from_legacy_master, normalize_profile

ROOT = Path(__file__).resolve().parent.parent
needs_typst = pytest.mark.skipif(render.find_typst() is None and importlib.util.find_spec("typst") is None,
                                reason="Typst nicht installiert")


def _profile():
    return from_legacy_master(json.loads((Path(__file__).resolve().parent / "fixtures" / "sample_profile.json").read_text(encoding="utf-8")))


def _structured(profile, **cl):
    ai = {"job": {"company": "Beispiel AG", "job_title": "Werkstudent Frontend", "zip_city": "10115 Berlin"},
          "summary": "Ich entwickle Webanwendungen.",
          "experience": [{"ref": f"E{i}", "bullets": j["bullets"][:2]} for i, j in enumerate(profile["experience"], 1)],
          "skills": [{"ref": "S1", "items": profile["skills"][0]["items"]}],
          "cover_letter": {"p1": "Eins.", "p2": "Zwei.", "p3": "Drei.", "p4": "Mein Portfolio zeigt mehr.", **cl}}
    return generate.assemble(ai, profile, "Werkstudent")


def test_fonts_are_real_truetype():
    for f in (ROOT / "fonts").glob("*.ttf"):
        head = f.read_bytes()[:4]
        assert head in (b"\x00\x01\x00\x00", b"OTTO", b"true"), f"{f.name} ist keine Schriftdatei"


def test_render_data_contents():
    p = _profile()
    s = _structured(p)
    d = render.build_render_data(s, p, accent="#123456", font="Lexend", show_photo=True, show_links=False,
                                 has_photo=False, has_signature=False)
    assert d["photo"] == "" and d["show_links"] is False and d["portfolio_url"] == ""
    assert d["date_line"].startswith("Köln, ")
    assert d["cover_letter"]["subject"] == "Bewerbung als Werkstudent Frontend"
    assert d["cover_letter"]["recipient_lines"] == ["10115 Berlin"]
    assert len(d["experience"]) == len(p["experience"])


def test_prepare_photo_makes_square_jpeg():
    img = Image.new("RGB", (300, 500), "red")
    b = io.BytesIO()
    img.save(b, "PNG")
    out = Image.open(io.BytesIO(render.prepare_photo(b.getvalue(), size=200)))
    assert out.size == (200, 200) and out.format == "JPEG"


def test_prepare_signature_transparent():
    img = Image.new("RGB", (200, 100), "white")
    img.paste((0, 0, 0), (50, 40, 150, 60))
    b = io.BytesIO()
    img.save(b, "PNG")
    out = Image.open(io.BytesIO(render.prepare_signature(b.getvalue())))
    assert out.mode == "RGBA" and out.size == (100, 20)


@needs_typst
def test_render_pdf_three_pages_with_photo_and_special_chars():
    p = _profile()
    s = _structured(p, p2="Sonderzeichen #include *fett* _x_ $5 // @user <tag> [1] \\ ~ = Test.")
    s["cover_letter"]["company"] = "#Firma & *Co*"
    photo = io.BytesIO()
    Image.new("RGB", (400, 600), "blue").save(photo, "JPEG")
    pdf = render.render_pdf(s, p, photo=render.prepare_photo(photo.getvalue()),
                            signature=(Path(__file__).resolve().parent / "fixtures" / "signature.png").read_bytes())
    assert pdf[:4] == b"%PDF"
    assert render.count_pages(pdf) == 3
    pages = render.pdf_text(pdf)
    assert "#Firma & *Co*" in pages[1]
    assert "$5 // @user <tag> [1]" in pages[1]
    assert "Lebenslauf" in pages[2] and "Nordwind Commerce" in pages[2]


@needs_typst
def test_render_minimal_profile():
    p = normalize_profile({"personal": {"name": "Max Mustermann", "email": "max@example.de"},
                           "education": [{"institution": "Gesamtschule", "degree": "Abitur", "end": "2024"}]})
    s = generate.assemble({"cover_letter": {"p1": "Hallo."}}, p, "Ausbildung")
    pdf = render.render_pdf(s, p)
    assert render.count_pages(pdf) == 3


def test_render_with_python_typst_fallback(monkeypatch):
    """Ohne Typst-CLI (z.B. Streamlit Cloud) wird das Python-Paket genutzt."""
    pytest.importorskip("typst")
    monkeypatch.setattr(render, "find_typst", lambda: None)
    p = _profile()
    pdf = render.render_pdf(_structured(p), p, signature=(Path(__file__).resolve().parent / "fixtures" / "signature.png").read_bytes())
    assert render.count_pages(pdf) == 3
    assert "Lebenslauf" in render.pdf_text(pdf)[2]


@pytest.mark.skipif(render.find_typst() is None, reason="prüft den Aufruf der Typst-CLI")
def test_icons_follow_accent_color(monkeypatch, tmp_path):
    """Icons werden in der Akzentfarbe eingefärbt (nicht fest Petrol)."""
    captured = {}
    real_run = render.subprocess.run

    def spy(cmd, **kw):
        icons = Path(cmd[-2]).parent / "icons"
        captured["svg"] = (icons / "linkedin.svg").read_text(encoding="utf-8")
        return real_run(cmd, **kw)
    monkeypatch.setattr(render.subprocess, "run", spy)
    p = _profile()
    render.render_pdf(_structured(p), p, accent="#7A1F2B")
    assert "#7A1F2B" in captured["svg"] and "#0F5F6E" not in captured["svg"]
