import json

import pytest

from smartresume import generate, llm, quality
from smartresume.profile import normalize_profile


@pytest.fixture
def profile():
    return normalize_profile({
        "personal": {"name": "Anna Muster", "email": "anna@example.de", "zip_city": "50667 Köln",
                     "links": [{"label": "Portfolio", "url": "https://anna.dev"}]},
        "experience": [
            {"company": "ACME GmbH", "role": "Junior Developer", "start": "01/2023", "end": "Heute",
             "location": "Köln", "bullets": ["Entwicklung von React-Komponenten", "Betreuung des Shopify-Shops",
                                              "Einführung automatisierter Tests"]},
            {"company": "Café Sonne", "role": "Aushilfe", "start": "2019", "end": "2022",
             "location": "Bonn", "bullets": ["Kassenabrechnung", "Kundenservice"]},
        ],
        "education": [{"institution": "TH Köln", "degree": "B.Sc. Informatik", "start": "2022", "end": "heute"}],
        "skills": [{"category": "Frontend", "items": ["React", "TypeScript", "CSS"]},
                   {"category": "Tools", "items": ["Git", "Jira"]}],
        "languages": [{"language": "Deutsch", "level": "Muttersprache"}],
        "preferences": {"student_status": "Eingeschrieben, 5. Semester", "hours_per_week": "20"},
    })


AI_ANSWER = {
    "job": {"company": "Beispiel AG", "job_title": "Werkstudent Frontend", "contact_person": "Frau Weber",
            "zip_city": "10115 Berlin", "asks_salary": False},
    "summary": "Ich entwickle seit 2023 React-Anwendungen. Neben dem Studium bringe ich Praxis mit.",
    "experience": [
        {"ref": "E1", "bullets": ["Entwicklung von React-Komponenten für den Kundenbereich",
                                  "Einführung automatisierter Tests mit sehr vielen zusätzlichen Worten die "
                                  "das Limit sprengen und gekürzt werden müssen"]},
        # E2 fehlt absichtlich → Fallback auf Profil
    ],
    "skills": [{"ref": "S1", "items": ["React", "TypeScript", "Kubernetes"]},  # Kubernetes erfunden
               {"ref": "S9", "category": "Erfunden", "items": ["Docker"]}],
    "cover_letter": {"salutation": "Sehr geehrte Frau Weber,", "p1": "a", "p2": "b", "p3": "c", "p4": "d"},
    "gaps": ["Vue.js"],
}


def test_assemble_takes_facts_from_profile(profile):
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Werkstudent", extra_info="Figma")
    assert [e["company"] for e in s["experience"]] == ["ACME GmbH", "Café Sonne"]
    assert s["experience"][0]["dates"] == "01/2023 – Heute"
    assert s["experience"][1]["bullets"] == ["Kassenabrechnung", "Kundenservice"]  # Fallback
    assert all(len(b) <= generate.MAX_BULLET_CHARS for e in s["experience"] for b in e["bullets"])
    assert s["education"][0]["degree"] == "B.Sc. Informatik"
    cats = {x["category"]: x["items"] for x in s["skills"]}
    assert cats["Frontend"] == "React, TypeScript"  # Kubernetes rausgefiltert
    assert "Erfunden" not in cats                      # Docker steht nirgends
    assert cats["Weitere Kenntnisse"] == "Figma"
    assert cats["Sprachen"] == "Deutsch (Muttersprache)"
    cl = s["cover_letter"]
    assert cl["company"] == "Beispiel AG" and cl["city"] == "10115 Berlin"
    assert cl["subject"] == "Bewerbung als Werkstudent Frontend"  # kein doppeltes "(Werkstudent)"
    assert cl["salutation"] == "Sehr geehrte Frau Weber,"


def test_assemble_subject_and_salutation_fallbacks(profile):
    ai = {"job": {"job_title": "Sachbearbeiter"}, "cover_letter": {"salutation": "Yo"}}
    s = generate.assemble(ai, profile, "Teilzeit")
    assert s["cover_letter"]["subject"] == "Bewerbung als Sachbearbeiter (Teilzeit)"
    assert s["cover_letter"]["salutation"] == "Sehr geehrte Damen und Herren,"
    assert s["skills"][0]["category"] == "Frontend"  # Fallback, wenn KI keine Skills liefert


def test_shorten_bullet():
    assert generate.shorten_bullet("Kurz.") == "Kurz"
    long = "Konzeption und Umsetzung eines Onlineshops inkl. Zahlungsanbindung und Versandlogik für Kunden"
    out = generate.shorten_bullet(long, 60)
    assert len(out) <= 60 and not out.endswith(("…", ",", "-"))


def test_clean_job_text():
    raw = "Cookie-Einstellungen\nJetzt bewerben\nWir suchen dich!\nWir suchen dich!\n\nAufgaben:\n- React\nab\n"
    out = generate.clean_job_text(raw)
    assert "Cookie" not in out and out.count("Wir suchen dich!") == 1 and "Aufgaben:" in out
    assert len(generate.clean_job_text("x" * 50 + "\n" + "y" * 20000, limit=1000)) <= 1020


def test_quality_flags_inflation_weakness_and_facts(profile):
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    s["cover_letter"].update(
        p1="Als erfahrener Experte mit 10 Jahren Erfahrung bin ich hochmotiviert.",
        p2="Leider habe ich wenig Erfahrung mit Vue. Ich steigerte den Umsatz um 37 %.",
        p3="[Kündigungsfrist]", p4="Meine Gehaltsvorstellung liegt bei 50.000 €.")
    f = quality.check_application(s, profile, job_text="Wir suchen React-Entwickler.")
    msgs = " | ".join(x["msg"] for x in f)
    assert "Experte" in msgs or "experte" in msgs
    assert "10 Jahre" in msgs
    assert "leider" in msgs
    assert "hochmotiviert" in msgs
    assert "„37“" in msgs                  # erfundene Zahl
    assert "Platzhalter" in msgs
    assert "Gehalt" in msgs
    # 10 Jahre, Platzhalter, Gehalt, erfundene Zahlen 10/37/50.000, „Experte“ (ausdrücklich verboten)
    assert len(quality.blocking_problems(f)) == 7


def test_quality_clean_text_has_no_errors(profile):
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    s["cover_letter"].update(
        p1="In Ihrer Anzeige suchen Sie Unterstützung beim Ausbau Ihres React-Frontends. "
           "Genau daran arbeite ich seit 2023 bei der ACME GmbH.",
        p2="Dort entwickle ich React-Komponenten und habe automatisierte Tests eingeführt. "
           "Neue Funktionen stimme ich direkt mit dem Kundenservice ab. "
           "Fehlerberichte aus dem Support arbeite ich innerhalb eines Sprints ab.",
        p3="Ich kläre Anforderungen früh und liefere in kleinen, prüfbaren Schritten. "
           "Rückfragen stelle ich lieber am ersten Tag als am letzten.",
        p4="Ich freue mich auf ein Gespräch, in dem ich Ihnen mein Portfolio zeigen kann. "
           "Gern bringe ich ein laufendes Beispielprojekt mit.")
    f = quality.check_application(s, profile, job_text="React")
    assert [x for x in f if x["level"] == "error"] == []


def _fake(monkeypatch, answers):
    calls = []

    def fake(cfg, key, system, user, json_mode, max_tokens, temperature):
        calls.append((system, user))
        return llm.LLMResult(json.dumps(answers.pop(0)) if not isinstance(answers[0], str) else answers.pop(0),
                             1000, 300, "fake")
    monkeypatch.setitem(llm.PROVIDERS, "fake", fake)
    return calls


CFG = {"label": "Fake", "provider": "fake", "model": "fake", "key_env": "K"}


def test_generate_end_to_end_with_repair(profile, monkeypatch):
    bad = json.loads(json.dumps(AI_ANSWER))
    bad["cover_letter"]["p4"] = "Gerne nenne ich [Gehaltsvorstellung]."
    fixed = {"salutation": "Sehr geehrte Frau Weber,", "p1": "a", "p2": "b", "p3": "c",
             "p4": "Ich freue mich auf ein Gespräch."}
    calls = _fake(monkeypatch, [bad, fixed])
    res = generate.generate_application(profile, "Cookie\nWir suchen Werkstudent Frontend (React)", "Werkstudent",
                                        CFG, "key", extra_info="Figma")
    assert res.repaired and res.structured["cover_letter"]["p4"] == "Ich freue mich auf ein Gespräch."
    assert res.input_tokens == 2000 and res.output_tokens == 600
    system, user = calls[0]
    assert "Portfolio" in system and "genau 2 Bullets" in system
    assert "E1.1 Entwicklung von React-Komponenten" in user
    assert "Werkstudent" in user and "Figma" in user and "Cookie" not in user


def test_generate_no_repair_needed(profile, monkeypatch):
    calls = _fake(monkeypatch, [json.loads(json.dumps(AI_ANSWER))])
    res = generate.generate_application(profile, "Stelle", "Vollzeit", CFG, "key")
    assert not res.repaired and len(calls) == 1


# --- Regressionen aus dem Live-Test (11/2026) -------------------------------
def test_number_check_is_exact_not_substring(profile):
    """GPT-OSS erfand 'Ladezeit um 20 % gesenkt' – 20 steckt in 2020, darf aber nicht durchrutschen."""
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    s["cover_letter"]["p2"] = "Bei ACME sank die Ladezeit dadurch um 23 %."  # 23 steckt in 2023
    f = quality.check_application(s, profile, job_text="Stelle seit 2023")
    assert any("„23“" in x["msg"] and x["level"] == "error" for x in f)
    s["cover_letter"]["p2"] = "Seit 2023 entwickle ich React-Komponenten."  # 2023 steht im Profil
    assert not any("„2023“" in x["msg"] for x in quality.check_application(s, profile))


def test_contradiction_learned_missing_skill(profile):
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    s["cover_letter"]["p2"] = ("Mit Vue.js habe ich noch nicht produktiv gearbeitet – das Framework habe ich mir "
                               "eigenständig erschlossen.")
    assert any("Widerspruch" in m for m in quality.blocking_problems(quality.check_application(s, profile)))
    s["cover_letter"]["p2"] = ("Mit Vue.js habe ich noch nicht gearbeitet; meine Erfahrung mit React "
                               "erleichtert mir den Einstieg.")
    assert not any("Widerspruch" in x["msg"] for x in quality.check_application(s, profile))


def test_salary_and_start_are_deterministic(profile):
    profile["preferences"].update(salary_expectation="39.000–42.000 € brutto jährlich", availability="sofort")
    job = "Bitte nenne uns deine Gehaltsvorstellung sowie deinen frühestmöglichen Eintrittstermin."
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit", job_text=job)
    p4 = s["cover_letter"]["p4"]
    assert p4.startswith("d ") and "39.000–42.000 € brutto jährlich" in p4 and "ab sofort" not in p4
    assert "Ein Eintritt ist sofort möglich." in p4
    s2 = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit", job_text="Wir suchen dich.")
    assert s2["cover_letter"]["p4"] == "d"  # nicht gefragt → nichts ergänzt
    f = quality.check_application(s, profile, job_text=job)
    assert not [x for x in f if x["level"] == "error"]


def test_clean_job_title():
    assert generate.clean_job_title("Frontend Developer (m/w/d) – Vue.js") == "Frontend Developer – Vue.js"
    assert generate.clean_job_title("Sachbearbeiter (w/m/d)") == "Sachbearbeiter"
    assert generate.clean_job_title("Koch (all genders)") == "Koch (all genders)"
    assert generate.clean_job_title("Pflegekraft (M/W/D) Teilzeit") == "Pflegekraft Teilzeit"


def test_invented_skill_category_is_mapped(profile):
    ai = json.loads(json.dumps(AI_ANSWER))
    ai["skills"] = [{"category": "Projektmanagement", "items": ["Git", "Jira"]}]
    s = generate.assemble(ai, profile, "Vollzeit")
    assert s["skills"][0] == {"category": "Tools", "items": "Git, Jira"}


def test_du_sie_mix_is_error(profile):
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    s["cover_letter"].update(salutation="Sehr geehrte Frau Weber,", p1="Für eures Kundenportal bringe ich React mit.")
    assert any("Du/Sie" in m for m in quality.blocking_problems(quality.check_application(s, profile)))
    s["cover_letter"].update(salutation="Hallo Julia,", p1="Für euer Kundenportal bringe ich React mit.")
    assert not any("Du/Sie" in x["msg"] for x in quality.check_application(s, profile))


def test_exotic_hyphens_normalized(profile):
    ai = json.loads(json.dumps(AI_ANSWER))
    ai["summary"] = "Shopify\u2011System und\u202fNext.js"
    assert generate.assemble(ai, profile, "Vollzeit")["summary"] == "Shopify-System und Next.js"


def test_fact_check_parses_result(profile, monkeypatch):
    out = {"unsupported": [{"claim": "enge Abstimmung mit Backend-Teams", "reason": "Profil nennt kein Team"},
                           "kaputt", {"reason": "ohne claim"}]}
    _fake(monkeypatch, [out])
    s = generate.assemble(json.loads(json.dumps(AI_ANSWER)), profile, "Vollzeit")
    issues, tokens = generate.fact_check(s, profile, CFG, "k")
    assert issues == [out["unsupported"][0]] and tokens == 1300


def test_no_duplicate_skills_in_cv(profile):
    ai = json.loads(json.dumps(AI_ANSWER))
    first = profile["skills"][0]
    item = first["items"][0]
    # KI wählt denselben Skill in zwei Kategorien; Zusatz-Skills enthalten ihn (andere Schreibweise) + einen neuen
    ai["skills"] = [{"ref": "S1", "items": [item]}, {"ref": "S2", "items": [item] + profile["skills"][1]["items"][:1]}]
    s = generate.assemble(ai, profile, "Vollzeit", extra_info=f"{item.upper()}, Docker")
    all_items = [i.strip().lower() for cat in s["skills"] for i in cat["items"].split(",")]
    assert all_items.count(item.lower()) == 1
    assert "docker" in all_items and all_items.count("docker") == 1
    assert sum(1 for c in s["skills"] if c["category"] == "Weitere Kenntnisse") <= 1


def test_extra_skills_no_duplicates_in_other_spelling(profile):
    """Zusatz-Skills: „ms jira“ ist „Jira“ aus dem Profil, „docker, Docker“ nur einmal; Profil-Skills, die die KI
    nicht ausgewählt hat, landen in ihrer eigenen Kategorie statt unter „Weitere Kenntnisse“."""
    profile["skills"].append({"category": "Office", "items": ["MS Excel"]})
    ai = json.loads(json.dumps(AI_ANSWER))
    ai["skills"] = [{"ref": "S1", "items": ["React"]}, {"ref": "S2", "items": ["Jira"]}]
    s = generate.assemble(ai, profile, "Vollzeit", extra_info="ms jira, docker, Docker, Excel")
    items = [generate.skill_key(i) for c in s["skills"] for i in c["items"].split(", ")]
    assert items.count("jira") == 1 and items.count("docker") == 1 and items.count("excel") == 1
    assert "MS Excel" in str(s["skills"])                                   # Schreibweise aus dem Profil


def test_skills_land_in_their_own_category(profile):
    ai = json.loads(json.dumps(AI_ANSWER))
    cats = profile["skills"]
    a, b = cats[0]["items"][0], cats[1]["items"][0]
    # KI packt Skills aus zwei Kategorien unter einen erfundenen Namen + einen Skill, der nicht im Profil steht
    ai["skills"] = [{"category": "Technik", "items": [a, b, "Kubernetes"]}]
    s = generate.assemble(ai, profile, "Vollzeit")
    by = {c["category"]: c["items"] for c in s["skills"]}
    assert a in by[cats[0]["category"]] and b in by[cats[1]["category"]]
    assert "Technik" not in by and "Kubernetes" not in str(by)
