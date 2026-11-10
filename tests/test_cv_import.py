import io
import json

import pytest

from smartresume import cv_import, llm, render
from smartresume.profile import normalize_profile

CV_TEXT = """Max Mustermann
max@example.de | +49 170 1234567 | Musterweg 1, 50667 Köln
BERUFSERFAHRUNG
05/2021 – heute  Sachbearbeiter, Muster GmbH, Köln
- Bearbeitung von Kundenanfragen per Telefon und E-Mail
- Pflege der Stammdaten in SAP
AUSBILDUNG
2018 – 2021 Kaufmann für Büromanagement, IHK Köln
KENNTNISSE
MS Office, SAP, DATEV
Deutsch (Muttersprache), Englisch (B2)
"""


def test_extract_txt_and_too_short():
    assert "Muster GmbH" in cv_import.extract_text("cv.txt", CV_TEXT.encode())
    with pytest.raises(cv_import.CVImportError, match="kaum Text"):
        cv_import.extract_text("cv.txt", b"zu kurz")
    with pytest.raises(cv_import.CVImportError, match="PDF, DOCX"):
        cv_import.extract_text("cv.png", b"x" * 500)


def test_extract_docx_with_table():
    import docx
    d = docx.Document()
    for line in CV_TEXT.splitlines():
        d.add_paragraph(line)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "Führerschein"
    t.rows[0].cells[1].text = "Klasse B"
    b = io.BytesIO()
    d.save(b)
    text = cv_import.extract_text("lebenslauf.docx", b.getvalue())
    assert "Sachbearbeiter" in text and "Führerschein | Klasse B" in text


@pytest.mark.skipif(render.find_typst() is None, reason="Typst nicht installiert")
def test_extract_pdf_text_and_photo():
    # Eigenes PDF mit Text + Foto erzeugen (über unseren Renderer)
    from PIL import Image
    from smartresume import generate
    p = normalize_profile({"personal": {"name": "Max Mustermann", "email": "max@example.de"},
                           "experience": [{"company": "Muster GmbH", "role": "Sachbearbeiter",
                                           "bullets": ["Pflege der Stammdaten in SAP"]}]})
    s = generate.assemble({"summary": "Kaufmann mit SAP-Erfahrung.",
                           "cover_letter": {"p1": "Text " * 40}}, p, "Vollzeit")
    img = io.BytesIO()
    Image.new("RGB", (400, 400), (10, 120, 200)).save(img, "JPEG")
    pdf = render.render_pdf(s, p, photo=render.prepare_photo(img.getvalue()))
    text = cv_import.extract_text("x.pdf", pdf)
    assert "Muster GmbH" in text
    photos = cv_import.extract_photo_candidates("x.pdf", pdf)
    assert len(photos) >= 1
    assert cv_import.extract_photo_candidates("x.docx", b"nope") == []


def test_parse_cv_with_fake_ai(monkeypatch):
    answer = {"personal": {"name": "Max Mustermann", "email": "max@example.de", "zip_city": "50667 Köln"},
              "experience": [{"company": "Muster GmbH", "role": "Sachbearbeiter", "start": "05/2021", "end": "Heute",
                              "bullets": ["Bearbeitung von Kundenanfragen", "Pflege der Stammdaten in SAP"]}],
              "skills": [{"category": "Software", "items": ["MS Office", "SAP", "DATEV"]}],
              "languages": [{"language": "Englisch", "level": "B2"}]}
    seen = {}

    def fake(cfg, key, system, user, json_mode, max_tokens, temperature):
        seen["system"], seen["user"] = system, user
        return llm.LLMResult(json.dumps(answer), 900, 400, "fake")
    monkeypatch.setitem(llm.PROVIDERS, "fake", fake)
    prof, tokens = cv_import.parse_cv_with_ai(CV_TEXT, {"label": "F", "provider": "fake", "model": "f"}, "k")
    assert prof["personal"]["name"] == "Max Mustermann"
    assert prof["experience"][0]["bullets"][1] == "Pflege der Stammdaten in SAP"
    assert tokens == 1300
    assert "NICHTS erfinden" in seen["system"] and "Muster GmbH" in seen["user"]


def test_merge_profiles_keeps_existing_and_adds_new():
    base = normalize_profile({
        "personal": {"name": "Max", "email": "", "links": [{"url": "https://github.com/max"}]},
        "experience": [{"company": "Muster GmbH", "role": "Sachbearbeiter", "bullets": ["A"]}],
        "skills": [{"category": "Software", "items": ["SAP"]}]})
    inc = normalize_profile({
        "personal": {"name": "Maximilian", "email": "max@example.de",
                     "links": [{"url": "https://github.com/max/"}, {"url": "https://max.de"}]},
        "experience": [{"company": "Muster  GmbH", "role": "Sachbearbeiter", "bullets": ["B"]},
                       {"company": "Neu AG", "role": "Azubi"}],
        "skills": [{"category": "software", "items": ["sap", "DATEV"]}, {"category": "Office", "items": ["Excel"]}]})
    m = cv_import.merge_profiles(base, inc)
    assert m["personal"]["name"] == "Max" and m["personal"]["email"] == "max@example.de"
    assert len(m["personal"]["links"]) == 2
    assert [e["company"] for e in m["experience"]] == ["Muster GmbH", "Neu AG"]
    assert m["skills"][0]["items"] == ["SAP", "DATEV"]
    assert m["skills"][1]["category"] == "Office"
