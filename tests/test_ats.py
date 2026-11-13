import importlib.util
import io
import json

import pytest

from smartresume import ats, generate, render
from smartresume.profile import normalize_profile

PROFILE = normalize_profile({
    "personal": {"name": "Anna Beispiel", "email": "anna@example.com", "zip_city": "50667 Köln"},
    "experience": [{"company": "Muster AG", "role": "Sachbearbeiterin", "start": "01/2022", "end": "Heute",
                    "bullets": ["Auswertungen mit Excel", "Kundenbetreuung am Telefon"]}],
    "skills": [{"category": "Office", "items": ["Excel", "Word"]}, {"category": "Sonstiges", "items": ["SAP"]}],
})
AI = {"job": {"company": "Firma GmbH", "job_title": "Sachbearbeiter (m/w/d)"}, "summary": "Ich arbeite genau.",
      "experience": [{"ref": "E1", "bullets": ["Auswertungen mit Excel"]}],
      "skills": [{"ref": "S1", "items": ["MS Excel"]}],
      "cover_letter": {"p1": "Eins.", "p2": "Zwei.", "p3": "Drei.", "p4": "Vier."},
      "keywords": [{"term": "MS Excel", "profile": "Excel"}, {"term": "SAP", "profile": "SAP"},
                   {"term": "Power BI", "profile": "Excel"},           # falsch zugeordnet (nur verwandt)
                   {"term": "Kubernetes", "profile": "Kubernetes"},     # erfunden – steht nicht im Profil
                   {"term": "Word", "profile": ""}, "Buchhaltung"]}


def test_clean_keywords_only_trusts_real_profile_entries():
    kw = ats.clean_keywords(AI["keywords"], PROFILE)
    by = {k["term"]: k["profile"] for k in kw}
    assert by["MS Excel"] == "Excel" and by["SAP"] == "SAP"
    assert by["Kubernetes"] == ""            # KI-Behauptung verworfen
    assert by["Word"] == "Word"              # steht im Profil, KI hatte es übersehen
    assert by["Buchhaltung"] == ""


def test_assemble_uses_ad_wording_for_same_skill_and_reports():
    s = generate.assemble(json.loads(json.dumps(AI)), PROFILE, "Vollzeit")
    assert "MS Excel" in s["skills"][0]["items"] and "Excel," not in s["skills"][0]["items"]
    rep = {r["term"]: r["status"] for r in ats.report(s)}
    assert rep["MS Excel"] == "ok"
    assert rep["SAP"] == "addable" and rep["Word"] == "addable"
    assert rep["Kubernetes"] == "missing" and rep["Buchhaltung"] == "missing"
    before = ats.score(ats.report(s))
    ats.add_to_skills(s, "SAP")
    ats.add_to_skills(s, "SAP")             # kein Doppel
    after = ats.report(s)
    assert ats.score(after) > before
    assert sum(1 for c in s["skills"] if c["category"] == "Weitere Kenntnisse") == 1
    assert s["skills"][-1]["category"] != "Weitere Kenntnisse" or not PROFILE["languages"]
    assert ats.best_possible(after) < 100   # echte Lücken bleiben Lücken


def test_use_ad_wording_replaces_skill_item():
    s = {"skills": [{"category": "Office", "items": "Excel, Word"}], "keywords": []}
    ats.use_ad_wording(s, "MS Excel", "excel")
    assert s["skills"][0]["items"] == "MS Excel, Word"


@pytest.mark.skipif(render.find_typst() is None and importlib.util.find_spec("typst") is None,
                    reason="Typst nicht installiert")
def test_pdf_is_ats_friendly_and_splits():
    from pypdf import PdfReader
    p = normalize_profile({**PROFILE, "personal": {**PROFILE["personal"],
                                                  "links": [{"label": "LinkedIn", "url": "https://www.linkedin.com/in/anna/"}]}})
    s = generate.assemble(json.loads(json.dumps(AI)), p, "Vollzeit")
    pdf = render.render_pdf(s, p)
    r = PdfReader(io.BytesIO(pdf))
    assert r.metadata["/Title"] == "Bewerbung als Sachbearbeiter – Anna Beispiel"
    assert "MS Excel" in r.metadata["/Keywords"]
    letter, cv = render.split_pdf(pdf)
    cv_text = PdfReader(io.BytesIO(cv)).pages[0].extract_text()
    lines = cv_text.splitlines()
    assert lines[0] == "Lebenslauf" and lines[1].startswith("Anna Beispiel")   # Name auf dem einzelnen Lebenslauf
    assert "linkedin.com/in/anna" in cv_text                                # Link als Text lesbar
    assert "Sehr geehrte" in PdfReader(io.BytesIO(letter)).pages[0].extract_text()
    assert len(PdfReader(io.BytesIO(letter)).pages) + len(PdfReader(io.BytesIO(cv)).pages) == len(r.pages) - 1


def test_gaps_count_in_score():
    s = generate.assemble(json.loads(json.dumps({**AI, "gaps": ["Erfahrung mit Docker", "Buchhaltung (DATEV)"]})),
                          PROFILE, "Vollzeit")
    rep = ats.report(s)
    assert any(r["term"] == "Erfahrung mit Docker" and r["status"] == "missing" for r in rep)
    assert not any(r["term"] == "Buchhaltung (DATEV)" for r in rep)   # schon als Begriff „Buchhaltung“ enthalten


def test_weak_zwar_is_flagged():
    from smartresume import quality
    s = generate.assemble(json.loads(json.dumps(AI)), PROFILE, "Vollzeit")
    s["cover_letter"]["p2"] = "Mit Docker habe ich zwar noch nicht gearbeitet, aber ich lerne schnell."
    assert any("zwar" in f["msg"] for f in quality.check_application(s, PROFILE, "", "", 120))


def test_bridge_mention_is_marked_and_repetition_flagged():
    from smartresume import quality
    s = generate.assemble(json.loads(json.dumps(AI)), PROFILE, "Vollzeit")
    s["cover_letter"]["p2"] = "Mit Kubernetes habe ich noch nicht gearbeitet; meine Excel-Erfahrung hilft beim Einstieg."
    s["cover_letter"]["p3"] = ("Ich arbeite mich schnell in neue Themen ein. "
                               "Ich arbeite mich schnell und selbstständig in neue Themen ein.")
    rep = {r["term"]: r["status"] for r in ats.report(s)}
    assert rep["Kubernetes"] == "bridge"
    f = quality.check_application(s, PROFILE, "", "", 120)
    assert any(x["level"] == "error" and "Wiederholung" in x["msg"] for x in f)
    s["summary"] = "Ich bringe fundierte Kenntnisse mit."
    assert any(x["level"] == "error" and "fundiert" in x["msg"] for x in quality.check_application(s, PROFILE))
