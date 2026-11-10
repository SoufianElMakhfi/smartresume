import base64

import pytest

from smartresume import jobsearch as js

RAW = {
    "stellenangebotsTitel": "Werkstudent  IT-Support (m/w/d)",
    "firma": "Beispiel GmbH",
    "referenznummer": "123-ABC-S",
    "entfernung": 11,
    "datumErsteVeroeffentlichung": "2026-10-22",
    "eintrittszeitraum": {"von": "2026-11-01"},
    "stellenlokationen": [{"adresse": {"plz": "50667", "ort": "Köln"}}],
    "gehaltsspanneVon": 58000.0, "gehaltsspanneBis": 85000.0, "verguetungsangabe": "JAHRESGEHALT",
    "homeofficemoeglich": True,
}


def test_normalize():
    j = js.normalize(RAW)
    assert j["title"] == "Werkstudent IT-Support (m/w/d)"
    assert j["location"] == "50667 Köln" and j["distance"] == 11
    assert j["salary"] == "58.000–85.000 €/Jahr"
    assert j["homeoffice"] and not j["external"]
    assert j["url"] == "https://www.arbeitsagentur.de/jobsuche/jobdetail/123-ABC-S"
    ext = js.normalize({**RAW, "externeURL": "https://example.com/job"})
    assert ext["url"] == "https://example.com/job" and ext["external"]
    assert js.normalize({**RAW, "gehaltsspanneVon": None, "festgehalt": 15.5,
                         "verguetungsangabe": "STUNDENLOHN"})["salary"] == "15,50 €/Std."


def test_build_params_maps_employment_types():
    p = js.build_params("Frontend", "Köln", 25, "Vollzeit", 30)
    assert p["angebotsart"] == 1 and p["arbeitszeit"] == "vz" and p["umkreis"] == 25
    assert js.build_params("", "Köln", 25, "Werkstudent", 7)["was"] == "Werkstudent"
    assert js.build_params("IT", "Köln", 25, "Ausbildung", 7)["angebotsart"] == 4
    assert "umkreis" not in js.build_params("IT", "Köln", 0, "Vollzeit", 7)


def test_search_werkstudent_merges_second_query(monkeypatch):
    calls = []

    def fake_get(path, params=None, timeout=20):
        calls.append(params)
        if params.get("angebotsart") == 34:
            return {"maxErgebnisse": 2, "ergebnisliste": [
                {**RAW, "referenznummer": "A", "stellenangebotsTitel": "Praktikant IT"},
                {**RAW, "referenznummer": "B", "stellenangebotsTitel": "Werkstudium Informationssicherheit"}]}
        return {"maxErgebnisse": 2, "ergebnisliste": [
            {**RAW, "referenznummer": "B", "stellenangebotsTitel": "Werkstudium Informationssicherheit"},
            {**RAW, "referenznummer": "C", "stellenangebotsTitel": "Werkstudent IT-Sicherheit"}]}
    monkeypatch.setattr(js, "_get", fake_get)
    jobs, total = js.search("Informationssicherheit", "Köln", 25, "Werkstudent", 30)
    assert [j["ref"] for j in jobs] == ["B", "C", "A"]      # Werkstudent-Titel zuerst, keine Dubletten
    assert total == 3
    assert calls[1]["was"] == "Werkstudent Informationssicherheit" and "angebotsart" not in calls[1]


def test_search_errors(monkeypatch):
    import requests
    with pytest.raises(js.JobSearchError, match="Suchbegriff oder Ort"):
        js.search("", "")

    class R:
        status_code = 403
    monkeypatch.setattr(requests, "get", lambda *a, **k: R())
    with pytest.raises(js.JobSearchError, match="HTTP 403"):
        js.search("IT", "Köln")

    def boom(*a, **k):
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(js.JobSearchError, match="nicht erreichbar"):
        js.search("IT", "Köln")


def test_details_text(monkeypatch):
    seen = {}

    def fake_get(path, params=None, timeout=20):
        seen["path"] = path
        return {"stellenangebotsBeschreibung": "Ihre Aufgaben:\n- Support", "vertragsdauer": "BEFRISTET",
                "befristungInMonaten": 12}
    monkeypatch.setattr(js, "_get", fake_get)
    text = js.details_text(js.normalize(RAW))
    assert seen["path"].endswith(base64.b64encode(b"123-ABC-S").decode())
    assert text.startswith("Stellentitel: Werkstudent IT-Support (m/w/d)\nUnternehmen: Beispiel GmbH")
    assert "Vergütung laut Anzeige: 58.000–85.000 €/Jahr" in text and "Befristet: 12 Monate" in text
    assert text.endswith("Ihre Aufgaben:\n- Support")


def test_keywords_and_hits():
    profile = {"skills": [{"category": "Web", "items": ["Next.js / React", "TypeScript", "C++"]}],
               "projects": [{"stack": ["Flutter"]}], "languages": [{"language": "Englisch"}]}
    kw = js.profile_keywords(profile)
    assert kw == ["Next.js", "React", "TypeScript", "C++", "Flutter", "Englisch"]
    text = "Du kennst React und Typescript, C++ ist ein Plus. Englisch fließend. Kein ReactNative-Zwang."
    assert js.keyword_hits(text, kw) == ["React", "TypeScript", "C++", "Englisch"]


def test_already_applied():
    job = js.normalize(RAW)
    assert js.already_applied(job, [{"company": "Beispiel GmbH", "job_title": "Werkstudent IT-Support (m/w/d)"}])
    assert not js.already_applied(job, [{"company": "Andere AG", "job_title": "Werkstudent IT-Support"}])


def test_ratings_roundtrip():
    jobs = [js.normalize({**RAW, "referenznummer": r}) for r in ("A", "B", "C")]
    system, user = js.rating_prompts({"personal": {"headline": "Entwickler"}}, jobs, {"A": "Text A"})
    assert "### J1\nText A" in user and "### J2\nStellentitel:" in user and "JSON" in system
    check = js.validate_ratings(3)
    assert check({"ratings": []})
    assert check({"ratings": [{"id": "J1"}]})
    data = {"ratings": [{"id": "J1", "score": 120, "reason": "passt", "missing": ["Java", "SAP", "Go", "Rust"]},
                        {"id": "J3", "score": "40", "reason": "Lücken"}, {"id": "J9", "score": 99}]}
    assert not check(data)
    r = js.apply_ratings(data, jobs)
    assert r == {"A": {"score": 100, "reason": "passt", "missing": ["Java", "SAP", "Go"]},
                 "C": {"score": 40, "reason": "Lücken", "missing": []}}
