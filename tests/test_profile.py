import json
from datetime import date
from pathlib import Path

from smartresume.profile import (
    compact_profile_text, empty_profile, from_legacy_master, is_profile_usable,
    normalize_profile, profile_city, total_experience_years,
)

ROOT = Path(__file__).resolve().parent.parent


def test_empty_profile_roundtrip():
    assert normalize_profile(empty_profile()) == empty_profile()
    assert normalize_profile(None) == empty_profile()


def test_normalize_coerces_types_and_drops_junk():
    p = normalize_profile({
        "personal": {"name": "  Anna  ", "links": [{"url": "github.com/anna"}, {"label": "x"}]},
        "experience": [{"company": "ACME", "bullets": "Eins\nZwei; Drei"}, "kaputt", {}],
        "skills": [{"category": "Leer", "items": []}, {"category": "Tools", "items": "Excel, Word (Office 365)"}],
        "design": {"accent_color": "rot"},
    })
    assert p["personal"]["name"] == "Anna"
    assert p["personal"]["links"] == [{"label": "GitHub", "url": "https://github.com/anna"}]
    assert len(p["experience"]) == 1
    assert p["experience"][0]["bullets"] == ["Eins", "Zwei", "Drei"]
    assert p["skills"] == [{"category": "Tools", "items": ["Excel", "Word (Office 365)"]}]
    assert p["design"]["accent_color"] == ""


def test_usable_check():
    assert "Name" in is_profile_usable(empty_profile())
    p = empty_profile()
    p["personal"].update(name="Anna", email="a@b.de")
    p["education"] = [{"institution": "Schule"}]
    assert any("Nachname" in m for m in is_profile_usable(p))   # nur Vorname reicht nicht
    p["personal"]["name"] = "Anna Beispiel"
    assert is_profile_usable(p) == ["Telefonnummer"]                  # Telefon ist Pflicht
    p["personal"]["phone"] = "0151 2345678"
    assert is_profile_usable(p) == []


def test_link_platforms_pick_icon_by_choice_or_address():
    from smartresume.profile import guess_link_label, link_icon
    assert link_icon("XING", "https://example.com/me") == "xing"            # gewählte Plattform zählt
    assert link_icon("", "https://www.instagram.com/anna") == "instagram"   # sonst die Adresse
    assert link_icon("Portfolio", "https://anna.dev") == "globe"
    assert guess_link_label("https://twitter.com/anna") == "X (Twitter)"
    assert guess_link_label("https://x.com/anna") == "X (Twitter)"
    icons = {p.stem for p in (ROOT / "icons").glob("*.svg")}
    from smartresume.profile import LINK_PLATFORMS
    assert {icon for _, icon, _ in LINK_PLATFORMS} <= icons                 # jedes Icon existiert


def test_experience_years_merges_overlaps():
    p = normalize_profile({"experience": [
        {"company": "A", "start": "01/2020", "end": "12/2021"},
        {"company": "B", "start": "06/2021", "end": "12/2022"},  # überlappt
    ]})
    assert 2.9 <= total_experience_years(p) <= 3.1


def test_experience_years_heute():
    y = date.today().year
    p = normalize_profile({"experience": [{"company": "A", "start": f"01/{y - 1}", "end": "Heute"}]})
    assert 0.9 <= total_experience_years(p) <= 2.0


def test_city():
    p = empty_profile()
    p["personal"]["zip_city"] = "51069 Köln"
    assert profile_city(p) == "Köln"


def test_import_master_profile_format():
    legacy = json.loads((Path(__file__).resolve().parent / "fixtures" / "sample_profile.json").read_text(encoding="utf-8"))
    p = from_legacy_master(legacy)
    assert p["personal"]["name"] == "Max Mustermann"
    assert p["personal"]["zip_city"].endswith("Köln")
    assert len(p["experience"]) == len(legacy["experience"])
    assert all(job["bullets"] for job in p["experience"])
    assert any(s["category"] == "Frontend" for s in p["skills"])
    assert not any(s["category"].lower() == "sprachen" for s in p["skills"])
    assert p["writing_style"]["forbidden_phrases"]
    text = compact_profile_text(p)
    assert "E1.1" in text and "A1:" in text and "S1 " in text
    # Kompakter als das alte JSON-Dumping
    assert len(text) < len(json.dumps(legacy, ensure_ascii=False, indent=2)) * 0.6


def test_skills_are_deduplicated_and_added_once():
    from smartresume.profile import add_skills
    p = normalize_profile({"skills": [{"category": "Web", "items": ["React", "react", "CSS"]},
                                      {"category": "web", "items": ["HTML"]},
                                      {"category": "Tools", "items": ["CSS", "Git"]},
                                      {"category": "Leer", "items": []}]})
    assert p["skills"] == [{"category": "Web", "items": ["React", "CSS", "HTML"]},
                           {"category": "Tools", "items": ["Git"]}]
    assert add_skills(p, ["git", "Docker", "Figma", "docker"]) == ["Docker", "Figma"]
    assert add_skills(p, ["Docker", "Jira"]) == ["Jira"]
    assert [s["category"] for s in p["skills"]].count("Weitere Kenntnisse") == 1
    assert p["skills"][-1]["items"] == ["Docker", "Figma", "Jira"]
