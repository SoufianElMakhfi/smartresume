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
    """Alter Testname, neues Verhalten: siehe test_search_finds_related_and_drops_unrelated."""
    calls = []

    def fake_get(path, params=None, timeout=20):
        calls.append(params)
        return {"maxErgebnisse": 2, "ergebnisliste": [
            {**RAW, "referenznummer": "A", "stellenangebotsTitel": "Praktikant IT"},
            {**RAW, "referenznummer": "B", "stellenangebotsTitel": "Werkstudium Informationssicherheit"},
            {**RAW, "referenznummer": "C", "stellenangebotsTitel": "Werkstudent IT-Sicherheit"}]}
    monkeypatch.setattr(js, "_get", fake_get)
    jobs, total = js.search("Informationssicherheit", "Köln", 25, "Werkstudent", 30)
    assert [j["ref"] for j in jobs] == ["B", "C"]    # Praktikum fliegt bei Werkstudent raus, keine Dubletten
    assert total == 2
    assert any(c.get("was") == "Werkstudent" and "angebotsart" not in c for c in calls)  # alle Werkstudentenstellen
    assert any("was" not in c and c.get("angebotsart") == 34 for c in calls)    # plus ganze Kategorie


def _job(ref, title, beruf="", date="2026-11-01"):
    return {**RAW, "referenznummer": ref, "stellenangebotsTitel": title, "hauptberuf": beruf,
            "datumErsteVeroeffentlichung": date}


def test_plan_expands_field_and_ignores_employment_words():
    p = js.plan("Werkstudent Software")
    assert p["words"] == ["software"] and p["fields"] == ["IT & Software"]
    assert p["queries"][0] == "Software" and {"Informatik", "Developer", "Fullstack"} <= set(p["queries"])
    assert js.plan("Personalentwicklung")["fields"] == ["Personal & HR"]          # nicht IT trotz „entwicklung“
    assert js.plan("Arbeitssicherheit")["fields"] == []                            # nicht IT-Sicherheit
    unknown = js.plan("Zahnmedizin")
    assert unknown["fields"] == [] and unknown["queries"] == ["Zahnmedizin"]


def test_search_finds_related_and_drops_unrelated(monkeypatch):
    pool = [
        _job("SW1", "Werkstudent Softwareentwicklung (m/w/d)", "Softwareentwickler/in", "2026-10-01"),  # Kompositum
        _job("SW2", "Werkstudent Java Fullstack Developer (m/w/d)", "Informatiker/in"),
        _job("SW3", "Werkstudent Standard Application Services", "Informatiker/in"),     # nur Berufsangabe passt
        _job("LOG", "Werkstudent (m/w/d) Logistik", "Helfer/in - Lagerwirtschaft"),      # BA-Volltext-Treffer
        _job("TAX", "Werkstudent Steuerberatung", "IT-Berater/in"),                      # Beruf passt, Titel nicht
        _job("HR", "Werkstudent HR Learning & Development", "Personalentwickler/in"),
        _job("TRN", "Trainee Softwareentwicklung", "Softwareentwickler/in"),             # kein Werkstudent
        _job("THS", "Masterarbeit Softwareentwicklung (m/w/d)", "Softwareentwickler/in"),  # Abschlussarbeit
    ]
    category_only = [_job("SHK", "Studentische Hilfskraft IT-Support", "Informatiker/in", "2026-09-01")]
    pages = []

    def fake_get(path, params=None, timeout=20):
        pages.append((params.get("was", ""), params["page"]))
        if params.get("was") == "Werkstudent":
            return {"maxErgebnisse": 150, "ergebnisliste": pool if params["page"] == 1 else []}
        if "was" not in params:                                   # ganze Kategorie ohne Suchwort
            return {"maxErgebnisse": 1, "ergebnisliste": category_only}
        return {"maxErgebnisse": 0, "ergebnisliste": []}
    monkeypatch.setattr(js, "_get", fake_get)
    jobs, total = js.search("Werkstudent Software", "Köln", 50, "Werkstudent", 30)
    assert [j["ref"] for j in jobs] == ["SW1", "SW2", "SHK", "SW3"]  # eigenes Wort > Fachgebiet > nur Beruf
    assert total == 4
    assert ("Werkstudent", 2) in pages                              # Folgeseite des Pools wird geholt
    assert ("Informatik", 1) in pages and ("Software", 1) in pages  # verwandte Begriffe mitgesucht


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


@pytest.mark.parametrize("text, mode", [
    ("Wir bieten 100 % Remote – arbeite von überall in Deutschland.", "remote"),
    ("Die Stelle ist vollständig im Homeoffice möglich.", "remote"),
    ("Remote-first Team, ortsunabhängig.", "remote"),
    ("2 Tage Homeoffice pro Woche, hybrides Arbeiten.", "hybrid"),
    ("Mobiles Arbeiten nach Absprache.", "hybrid"),
    ("Du übernimmst den Remote-Support unserer Kunden vor Ort.", "onsite"),   # kein Homeoffice
    ("Homeoffice ist bei dieser Stelle leider nicht möglich.", "onsite"),
    ("Moderner Arbeitsplatz in Köln.", "onsite"),
])
def test_work_mode_from_ad_text(text, mode):
    assert js.work_mode("Sachbearbeiter (m/w/d)", text) == mode


def test_search_filters_by_work_mode(monkeypatch):
    pool = [_job("R", "Softwareentwickler (m/w/d)"), _job("H", "Software Developer (m/w/d)"),
            _job("O", "Softwareentwicklerin (m/w/d)")]
    texts = {"R": "100 % remote", "H": "2 Tage Homeoffice", "O": "Arbeitsplatz in Köln"}
    seen = []

    def fake_get(path, params=None, timeout=20):
        seen.append(dict(params))
        return {"maxErgebnisse": 3, "ergebnisliste": pool}
    monkeypatch.setattr(js, "_get", fake_get)
    monkeypatch.setattr(js, "details_many", lambda jobs, workers=6: {j["ref"]: texts[j["ref"]] for j in jobs})

    jobs, _ = js.search("Software", "Köln", 200, "Vollzeit", 30, work_mode=js.HOMEOFFICE)
    assert {j["ref"] for j in jobs} == {"R", "H"}
    assert all(p.get("wo") == "Köln" and p.get("umkreis") == 200 for p in seen)

    seen.clear()
    got, stats = {}, {}
    jobs, _ = js.search("Software", "Köln", 25, "Vollzeit", 30, work_mode=js.REMOTE, texts=got, stats=stats)
    assert [j["ref"] for j in jobs] == ["R"] and jobs[0]["work_mode"] == "remote"
    assert all("wo" not in p for p in seen)                                  # remote: deutschlandweit
    assert any(p["was"] == "Software remote" for p in seen)
    assert got["R"] == "100 % remote" and stats == {"candidates": 3, "checked": 3}


def test_germany_wide_radius_drops_location():
    p = js.build_params("Software", "Köln", js.GERMANY, "Vollzeit", 30)
    assert "wo" not in p and "umkreis" not in p


def test_employment_type_from_query_wins():
    assert js.type_from_query("Werkstudent Student der Wirtschaftsinformatik") == "Werkstudent"
    assert js.type_from_query("Praktikum Marketing für Studierende") == "Praktikum"
    assert js.type_from_query("Ausbildung Fachinformatiker") == "Ausbildung"
    assert js.type_from_query("Vollzeit Wirtschaftsinformatik") == "Vollzeit"
    # „Student“ beschreibt die Person, nicht die Stelle – fertige Studenten suchen auch Vollzeit
    assert js.type_from_query("Student der Wirtschaftsinformatik") is None
    assert js.type_from_query("Controlling") is None


def test_own_choice_wins_no_guess_from_headline():
    from smartresume.profile import default_employment_type, normalize_profile
    student = normalize_profile({"personal": {"headline": "Student der Wirtschaftsinformatik"}})
    assert default_employment_type(student) == "Vollzeit"                      # keine Vermutung
    enrolled = normalize_profile({"preferences": {"student_status": "Eingeschrieben, 5. Semester"}})
    assert default_employment_type(enrolled) == "Werkstudent"                  # nur beim ersten Mal
    assert default_employment_type(enrolled, {"employment_type": "Vollzeit"}) == "Vollzeit"   # Wahl gemerkt


def test_search_term_suggestion_is_the_subject_not_the_person():
    from smartresume.profile import normalize_profile
    from smartresume.ui.jobs_page import _default_what
    assert _default_what(normalize_profile({"personal": {"headline": "Student der Wirtschaftsinformatik"}}))         == "Wirtschaftsinformatik"
    assert _default_what(normalize_profile({"personal": {"headline": "Kaufmann für Büromanagement"}}))         == "Kaufmann für Büromanagement"
