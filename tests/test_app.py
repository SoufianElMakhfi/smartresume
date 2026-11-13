"""UI-Tests: die echte app.py wird mit Streamlits AppTest durchgeklickt.
Die KI wird durch einen Fake-Provider ersetzt (schnell, deterministisch, kostenlos)."""
import importlib.util
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from smartresume import auth, config, db, llm, render

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_profile.json"
APP = str(ROOT / "app.py")

FAKE_AI = {
    "job": {"company": "Lumora GmbH", "job_title": "Frontend Developer (m/w/d)", "contact_person": "Frau Brandt",
            "zip_city": "50672 Köln"},
    "summary": "Ich baue Webanwendungen mit Next.js und Shopify.",
    "experience": [{"ref": "E1", "bullets": ["Technische Betreuung des Shopify-Systems", "Strategie im E-Commerce"]}],
    "skills": [{"ref": "S1", "items": ["Next.js / React", "TypeScript / JavaScript"]}],
    "cover_letter": {"salutation": "Sehr geehrte Frau Brandt,",
                     "p1": "Ihr Kundenportal weiterzuentwickeln passt zu dem, was ich bei Nordwind Commerce täglich tue.",
                     "p2": "Ich betreue dort das Shopify-System technisch und habe 95+ PageSpeed Scores erreicht.",
                     "p3": "Ich kläre Anforderungen früh und liefere in kleinen Schritten.",
                     "p4": "Ich freue mich auf ein Gespräch."},
    "gaps": ["Vue.js"],
}


SENT: dict[str, str] = {}  # E-Mail → zuletzt verschickter Code


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("SMARTRESUME_HOME", str(tmp_path))   # .env der Tests landet im Temp-Ordner
    monkeypatch.setattr(config, "_from_file", set())
    for k in [p["env"] for p in config.PROVIDERS]:           # echte Keys nie benutzen/verändern
        monkeypatch.setenv(k, "x")
        monkeypatch.delenv(k)
    SENT.clear()

    def fake_send(email, code, app_name="", link=""):
        SENT[email] = code
        return True
    monkeypatch.setattr(auth, "send_code", fake_send)
    models = tmp_path / "models.json"
    models.write_text(json.dumps([{"label": "Fake", "provider": "fake", "model": "fake-1", "key_env": "FAKE_KEY"}]))
    monkeypatch.setenv("SMARTRESUME_MODELS", str(models))
    monkeypatch.setenv("SMARTRESUME_BRANDING", str(tmp_path / "branding.json"))
    monkeypatch.setenv("FAKE_KEY", "x")
    calls = []

    def fake(cfg, key, system, user, json_mode, max_tokens, temperature):
        calls.append(system)
        return llm.LLMResult(json.dumps(FAKE_AI), 3000, 800, "fake-1")
    monkeypatch.setitem(llm.PROVIDERS, "fake", fake)
    db.init_db()
    return {"tmp": tmp_path, "calls": calls}


def _run(at):
    at.run()
    assert not at.exception, at.exception
    return at


def _btn(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"Button '{label}' nicht gefunden: {[b.label for b in at.button]}")


def _request_code(at, email):
    next(t for t in at.text_input if t.label == "E-Mail-Adresse").input(email)
    _btn(at, "Code senden").click()
    return _run(at)


def _enter_code(at, code):
    next(t for t in at.text_input if t.label == "Code").input(code)
    _btn(at, "Anmelden").click()
    return _run(at)


def _logged_in(at):
    return at.session_state["user"] if "user" in at.session_state else None


def _login(at, email="anna@example.com"):
    _request_code(at, email)
    return _enter_code(at, SENT[email])


def test_first_run_setup(env):
    at = _run(AppTest.from_file(APP, default_timeout=60))
    assert any("Ersteinrichtung" in s.value for s in at.subheader)
    assert not at.checkbox  # keine Altdaten-Übernahme mehr
    _request_code(at, "Max@Example.com ")
    assert "max@example.com" in SENT  # normalisiert
    _enter_code(at, SENT["max@example.com"])
    assert at.session_state.user["is_admin"] is True
    assert at.session_state.page == "profile"
    assert any("Mein Profil" in t.value for t in at.title)
    assert auth.user_from_session(at.session_state.session_token)["email"] == "max@example.com"


def test_login_wrong_and_right_code(env):
    db.create_user("anna@example.com")
    at = _run(AppTest.from_file(APP, default_timeout=60))
    _request_code(at, "kein-mail")
    assert any("gültige E-Mail" in e.value for e in at.error)
    _request_code(at, "anna@example.com")
    wrong = "000000" if SENT["anna@example.com"] != "000000" else "111111"
    _enter_code(at, wrong)
    assert any("stimmt nicht" in e.value for e in at.error)
    assert not _logged_in(at)
    _enter_code(at, SENT["anna@example.com"])
    assert at.session_state.user["email"] == "anna@example.com"
    assert at.session_state.page == "generate"


def test_new_email_creates_account(env):
    db.create_user("admin@example.com", is_admin=True)
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "neu@example.com")
    assert at.session_state.user["email"] == "neu@example.com"
    assert at.session_state.user["is_admin"] is False
    assert at.session_state.page == "profile"  # neue Nutzer starten beim Profil
    assert any("Mein Profil" in t.value for t in at.title)


def test_login_link_from_mail(env):
    db.create_user("anna@example.com")
    code = auth.request_code("anna@example.com")
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["email"] = "anna@example.com"
    at.query_params["code"] = code
    _run(at)
    assert at.session_state.user["email"] == "anna@example.com"
    at2 = AppTest.from_file(APP, default_timeout=60)  # Link ist nur einmal gültig
    at2.query_params["email"] = "anna@example.com"
    at2.query_params["code"] = code
    _run(at2)
    assert not _logged_in(at2) and at2.error


def test_invite_code_and_closed_registration(env):
    db.create_user("admin@example.com", is_admin=True)
    (env["tmp"] / "branding.json").write_text(json.dumps({"invite_code": "GEHEIM", "app_name": "JobBoost"}))
    at = _run(AppTest.from_file(APP, default_timeout=60))
    assert any("JobBoost" in m.value for m in at.markdown)  # Whitelabel-Name
    next(t for t in at.text_input if t.label.startswith("Einladungscode")).input("FALSCH")
    _request_code(at, "bernd@example.com")
    assert any("Einladungscode" in e.value for e in at.error) and not SENT
    next(t for t in at.text_input if t.label.startswith("Einladungscode")).input("GEHEIM")
    _request_code(at, "bernd@example.com")
    _enter_code(at, SENT["bernd@example.com"])
    assert at.session_state.user["email"] == "bernd@example.com"
    # bestehende Nutzer brauchen keinen Einladungscode
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "admin@example.com")
    assert at.session_state.user["is_admin"]

    (env["tmp"] / "branding.json").write_text(json.dumps({"allow_registration": False}))
    at = _run(AppTest.from_file(APP, default_timeout=60))
    _request_code(at, "fremd@example.com")
    assert any("kein Konto" in e.value for e in at.error) and "fremd@example.com" not in SENT


def _user_with_profile():
    uid = db.create_user("anna@example.com")
    from smartresume.profile import from_legacy_master
    db.save_profile(uid, data=from_legacy_master(json.loads(SAMPLE.read_text("utf-8"))))
    return uid


def test_incomplete_profile_blocks_generation(env):
    db.create_user("anna@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    assert any("unvollständig" in w.value for w in at.warning)


def test_profile_page_edit_and_save(env):
    uid = _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Mein Profil").click()
    _run(at)
    assert [t.label.split(": ", 1)[-1] for t in at.tabs] == ["Lebenslauf importieren", "Persönlich", "Werdegang",
                                                             "Kenntnisse", "Wünsche & Stil"]
    assert any("vollständig" in str(getattr(x, "value", "")) or "vollständig" in str(getattr(x, "text", ""))
               for x in at.get("progress"))
    assert next(t for t in at.text_input if t.label == "Vorname *").value == "Max"
    name_input = next(t for t in at.text_input if t.label == "Nachname *")
    assert name_input.value == "Mustermann"
    name_input.input("El Mustermann")
    _run(at)
    pers = db.get_profile(uid)["data"]["personal"]                    # sofort gespeichert, ohne Knopf
    assert (pers["first_name"], pers["last_name"], pers["name"]) == ("Max", "El Mustermann", "Max El Mustermann")
    # bleibt nach neuem Login (neue Sitzung) erhalten
    at2 = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at2, "Mein Profil").click()
    _run(at2)
    assert next(t for t in at2.text_input if t.label == "Nachname *").value == "El Mustermann"
    # Station hinzufügen und wieder entfernen
    n = len(db.get_profile(uid)["data"]["experience"])
    _btn(at, "Station hinzufügen").click()
    _run(at)
    assert len(at.session_state.draft["experience"]) == n + 1
    next(b for b in at.button if b.key and b.key.endswith("_experience0_del")).click()
    _run(at)
    assert len(at.session_state.draft["experience"]) == n


def test_profile_skills_as_chips_without_duplicates(env):
    uid = _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Mein Profil").click()
    _run(at)
    skills = db.get_profile(uid)["data"]["skills"]
    first, second = skills[0], skills[1]
    boxes = [m for m in at.multiselect if m.label == "Skills"]
    assert boxes[0].value == first["items"]
    # Über „Hinzufügen“: neuer Skill in Kategorie 2 + einer, der schon in Kategorie 1 steht (andere Schreibweise)
    at.text_input(key="skill_new").input(f"Docker, {first['items'][0].upper()}")
    at.selectbox(key="skill_cat").set_value(second["category"])
    _btn(at, "Hinzufügen").click()
    _run(at)
    saved = db.get_profile(uid)["data"]["skills"]
    assert "Docker" in saved[1]["items"]
    assert sum(i.lower() == first["items"][0].lower() for s in saved for i in s["items"]) == 1
    assert any("nicht doppelt" in i.value for i in at.info)
    assert at.text_input(key="skill_new").value == ""                  # Eingabefeld wieder leer
    # Entfernen per ✕
    boxes = [m for m in at.multiselect if m.label == "Skills"]
    boxes[0].set_value(first["items"][1:])
    _run(at)
    assert first["items"][0] not in db.get_profile(uid)["data"]["skills"][0]["items"]
    # Sprache hinzufügen: Niveau ist nicht vorausgewählt
    _btn(at, "Sprache hinzufügen").click()
    _run(at)
    lang_inputs = [t for t in at.text_input if t.placeholder == "z. B. Englisch"]
    lang_inputs[-1].input("Spanisch")
    _run(at)
    spanish = next(l for l in db.get_profile(uid)["data"]["languages"] if l["language"] == "Spanisch")
    assert spanish["level"] == ""
    # Link: Plattform aus der Liste, Icon passt dazu
    _btn(at, "Link hinzufügen").click()
    _run(at)
    link_boxes = [s for s in at.selectbox if s.label == "Plattform"]
    link_boxes[-1].set_value("XING")
    next(t for t in reversed(at.text_input) if t.label == "Link").input("https://www.xing.com/profile/Max")
    _run(at)
    links = db.get_profile(uid)["data"]["personal"]["links"]
    assert {"label": "XING", "url": "https://www.xing.com/profile/Max"} in links


@pytest.mark.skipif(render.find_typst() is None and importlib.util.find_spec("typst") is None,
                                reason="Typst nicht installiert")
def test_full_generation_flow(env):
    uid = _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=90)))
    job = next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext"))
    job.input("Frontend Developer (m/w/d) bei Lumora GmbH in Köln. Aufgaben: Vue.js, TypeScript, Performance. "
              "Bitte nenne deine Gehaltsvorstellung.")
    next(t for t in at.text_area if t.label.startswith("Zusätzliche Skills")).input("Figma")
    _btn(at, "Bewerbung erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "review", [e.value for e in at.error]
    g = at.session_state.gen
    assert g["structured"]["cover_letter"]["subject"] == "Bewerbung als Frontend Developer"
    assert "39.000–42.000" in g["structured"]["cover_letter"]["p4"]  # deterministisch ergänzt
    assert "Werkstudent" not in env["calls"][0]  # System-Prompt ist statisch
    assert any("Vue.js" in i.value for i in at.info)  # Lücke wird angezeigt
    assert db.user_token_total(uid) == 3800

    _btn(at, "PDF erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "done"
    pdf = at.session_state.gen_pdf
    assert render.count_pages(pdf) == 3
    assert "Lumora GmbH" in render.pdf_text(pdf)[1]

    # automatisch gespeichert – inkl. Stellenanzeige, Status „Erstellt“
    apps = db.list_applications(uid)
    assert len(apps) == 1 and apps[0]["company"] == "Lumora GmbH" and apps[0]["status"] == "Erstellt"
    assert "Vue.js" in db.get_application(uid, apps[0]["id"])["job_text"]
    assert [d.label for d in at.get("download_button") if not d.label.startswith("Entwurf")] == ["Bewerbungsmappe (PDF)"]
    # getrennt: Anschreiben + Lebenslauf (Wahl wird gemerkt)
    at.segmented_control(key="gen_format").set_value("Getrennt: Anschreiben + Lebenslauf")
    _run(at)
    assert [d.label for d in at.get("download_button") if not d.label.startswith("Entwurf")] == ["Anschreiben", "Lebenslauf"]
    assert db.get_user_settings(uid)["pdf_format"].startswith("Getrennt")
    # „Als beworben markieren“ setzt NUR den Status – keine zweite Bewerbung
    _btn(at, "Als beworben markieren").click()
    _run(at)
    apps = db.list_applications(uid)
    assert len(apps) == 1 and apps[0]["status"] == "Beworben"
    assert not any(b.label == "Als beworben markieren" for b in at.button)

    # Tracking-Seite: Status ändern und Bewerbung zum Bearbeiten öffnen
    _btn(at, "Meine Bewerbungen").click()
    _run(at)
    assert any("Lumora GmbH" in e.label for e in at.expander)
    _btn(at, "Bearbeiten").click()
    _run(at)
    assert at.session_state.page == "generate" and at.session_state.gen_step == "review"
    assert at.session_state.gen_app_id == apps[0]["id"]
    # erneut PDF erstellen → aktualisiert dieselbe Bewerbung statt eine neue anzulegen
    _btn(at, "PDF erstellen").click()
    _run(at)
    assert len(db.list_applications(uid)) == 1


def test_daily_limit(env):
    uid = _user_with_profile()
    (env["tmp"] / "branding.json").write_text(json.dumps({"daily_limit_per_user": 1}))
    db.log_usage(uid, "generate", "fake-1", 100)
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).input("Stellenanzeige " * 20)
    _btn(at, "Bewerbung erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "manual"           # Limit erreicht → Abo-Modus statt Abbruch
    assert any("Tageslimit" in i.value for i in at.info)
    assert not env["calls"]


def test_settings_and_admin_pages_render(env):
    db.create_user("chef@example.com", is_admin=True)
    db.create_user("bernd@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "chef@example.com")
    _btn(at, "Einstellungen").click()
    _run(at)
    assert any("Einstellungen" in t.value for t in at.title)
    _btn(at, "Verwaltung").click()
    _run(at)
    assert any("Verwaltung" in t.value for t in at.title)


def test_non_admin_has_no_admin_page(env):
    db.create_user("bernd@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "bernd@example.com")
    assert not any(b.label == "Verwaltung" for b in at.button)


# ---------------------------------------------------------------------------
# Abo-Modus (Kopieren & Einfügen über Gemini/ChatGPT)
# ---------------------------------------------------------------------------
JOB = ("Frontend Developer (m/w/d) bei Lumora GmbH in Köln. Aufgaben: Vue.js, TypeScript, Performance. "
       "Bitte nenne deine Gehaltsvorstellung.")


def _start_generation(at):
    next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).input(JOB)
    _btn(at, "Bewerbung erstellen").click()
    return _run(at)


def _paste_answer(at, text):
    next(t for t in at.text_area if t.label == "Antwort aus dem Chat").input(text)
    next(b for b in at.button if b.label.startswith("Antwort übernehmen")).click()
    return _run(at)


def test_without_api_key_uses_chat_mode(env, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")                      # keine KI-API eingerichtet
    _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    assert any("Ohne API-Key" in c.value for c in at.caption)          # vorab erklärt, wie es ohne Key geht
    assert any("KI per Kopieren" in m.value for m in at.markdown)      # Statusleiste
    _start_generation(at)
    assert at.session_state.gen_step == "manual"
    prompt = next(c.value for c in at.code)
    assert "AUSGABE" in prompt and "Lumora" in prompt and "json" in prompt.lower()   # Regeln + Auftrag
    _paste_answer(at, "Klar, hier ist es:")              # kein JSON → verständlicher Fehler + Korrektursatz
    assert at.session_state.gen_step == "manual" and at.error
    assert any("Antworte bitte erneut" in c.value for c in at.code)
    _paste_answer(at, "Hier dein Ergebnis:\n```json\n" + json.dumps(FAKE_AI, ensure_ascii=False) + "\n```")
    assert at.session_state.gen_step == "review"
    g = at.session_state.gen
    assert g["model"].startswith("Gemini/ChatGPT") and g["tokens"] == 0
    assert g["structured"]["cover_letter"]["company"] == "Lumora GmbH"
    assert "39.000–42.000" in g["structured"]["cover_letter"]["p4"]   # gleiche Nachbearbeitung wie per API
    assert not env["calls"]


def test_ai_failure_switches_to_chat_mode(env, monkeypatch):
    def broken(*a, **k):
        raise llm.LLMError("Kontingent erschöpft", transient=True)
    monkeypatch.setitem(llm.PROVIDERS, "fake", broken)
    _user_with_profile()
    at = _start_generation(_login(_run(AppTest.from_file(APP, default_timeout=60))))
    assert at.session_state.gen_step == "manual"
    assert any("Kontingent erschöpft" in i.value for i in at.info)
    assert at.session_state.gen_manual["job_text"] == JOB   # Eingaben bleiben erhalten


def test_cv_import_via_chat_mode(env, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")
    uid = db.create_user("anna@example.com")
    db.save_profile(uid, cv_text="Anna Beispiel, Köln. 2020-2024 Verkäuferin bei Muster AG.", cv_filename="cv.txt")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Mein Profil").click()
    _run(at)
    at.toggle(key="cv_use_ai").set_value(True)
    _run(at)
    assert any("noch keine KI verbunden" in i.value for i in at.info)   # vorab erklärt, wie es ohne KI geht
    _btn(at, "Gespeicherten Lebenslauf erneut auslesen (cv.txt)").click()
    _run(at)
    assert "Verkäuferin" in next(c.value for c in at.code)
    answer = {"personal": {"name": "Anna Beispiel", "zip_city": "Köln"},
              "experience": [{"company": "Muster AG", "role": "Verkäuferin", "start": "2020", "end": "2024",
                              "bullets": ["Beratung von Kundinnen und Kunden"]}]}
    # Antwort einfügen, wegnavigieren, zurück: die Antwort steht noch da
    pasted = json.dumps(answer, ensure_ascii=False)
    next(t for t in at.text_area if t.label == "Antwort aus dem Chat").input(pasted)
    _run(at)
    _btn(at, "Neue Bewerbung").click()
    _run(at)
    _btn(at, "Mein Profil").click()
    _run(at)
    assert next(t for t in at.text_area if t.label == "Antwort aus dem Chat").value == pasted
    _paste_answer(at, pasted)
    prof = db.get_profile(uid)["data"]
    assert prof["personal"]["name"] == "Anna Beispiel" and prof["experience"][0]["company"] == "Muster AG"
    assert at.session_state.profile_tab.endswith("Persönlich")          # springt direkt zu den übernommenen Daten
    assert any("Lebenslauf übernommen" in x.value for x in at.success)
    assert next(t for t in at.text_input if t.label == "Nachname *").value == "Beispiel"


def test_cv_import_without_ai_is_default(env, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")
    uid = db.create_user("anna@example.com")
    cv = ("Anna Ben Salah\nanna@example.com · 0151 2345678 · Lindenweg 3, 50667 Köln\nBERUFSERFAHRUNG\n"
          "Verkäuferin\n03/2020 – heute\nMuster AG, Köln\n• Beratung von Kundinnen und Kunden\n"
          "SPRACHEN\nDeutsch (Muttersprache), Englisch (B2)\n")
    db.save_profile(uid, cv_text=cv, cv_filename="cv.txt")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Mein Profil").click()
    _run(at)
    assert not any("noch keine KI verbunden" in i.value for i in at.info)   # kein Hinweis auf KI nötig
    _btn(at, "Gespeicherten Lebenslauf erneut auslesen (cv.txt)").click()
    _run(at)
    pers = db.get_profile(uid)["data"]["personal"]
    assert (pers["first_name"], pers["last_name"]) == ("Anna", "Ben Salah")
    assert db.get_profile(uid)["data"]["experience"][0]["company"] == "Muster AG"
    assert any("ohne KI" in x.value for x in at.success)
    assert next(t for t in at.text_input if t.label == "Nachname *").value == "Ben Salah"


# ---------------------------------------------------------------------------
# KI einrichten (Keys in der App eintragen)
# ---------------------------------------------------------------------------
def test_first_run_without_key_opens_setup_and_saves_key(env, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")
    models = [{"label": "Gemini Test", "provider": "fake", "model": "fake-1", "key_env": "GEMINI_API_KEY"}]
    (env["tmp"] / "models.json").write_text(json.dumps(models))
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "max@example.com")
    assert at.session_state.page == "setup"                    # erstes Konto ohne Key → zuerst KI einrichten
    assert any("KI einrichten" in t.value for t in at.title)
    next(t for t in at.text_input if t.key == "setup_GEMINI_API_KEY").input("AIza-test-123")
    _run(at)                                                   # Einfügen reicht: testen + speichern in einem
    assert any("Funktioniert" in m.value and "Gespeichert" in m.value for m in at.success)
    assert not any(b.label == "Speichern" for b in at.button)
    env_text = (env["tmp"] / ".env").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=" in env_text and "AIza-test-123" not in env_text   # verschlüsselt gespeichert
    assert config.is_set("GEMINI_API_KEY")
    _btn(at, "Neue Bewerbung").click()
    _run(at)
    assert not any("Ohne API-Key" in c.value for c in at.caption)       # sofort einsatzbereit
    assert any("KI automatisch" in m.value for m in at.markdown)


def test_setup_page_is_admin_only(env):
    db.create_user("chef@example.com", is_admin=True)
    db.create_user("bernd@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "bernd@example.com")
    assert not any(b.label == "KI einrichten" for b in at.button)


def test_job_search_rating_and_apply(env, monkeypatch):
    from smartresume import jobsearch
    uid = _user_with_profile()
    jobs = [jobsearch.normalize({"referenznummer": r, "stellenangebotsTitel": t, "firma": "Lumora GmbH",
                                 "stellenlokationen": [{"adresse": {"plz": "50672", "ort": "Köln"}}], "entfernung": d})
            for r, t, d in (("R1", "Backend Entwickler (m/w/d)", 3), ("R2", "Frontend Developer (m/w/d)", 8))]
    jobs[0]["relevance"], jobs[1]["relevance"] = 6, 2       # Reihenfolge vor der KI-Bewertung: R1, R2
    texts = {"R1": "Stellentitel: Backend Entwickler\nJava, Spring", "R2": "Stellentitel: Frontend Developer\n"
             "Unternehmen: Lumora GmbH\nAufgaben: React, TypeScript, Performance."}
    seen = {}

    def fake_search(**kw):
        seen.update(kw)
        return jobs, 2
    monkeypatch.setattr(jobsearch, "search", fake_search)
    monkeypatch.setattr(jobsearch, "details_many", lambda js_: texts)

    def fake_ai(cfg, key, system, user, json_mode, max_tokens, temperature):
        return llm.LLMResult(json.dumps({"ratings": [{"id": "J1", "score": 30, "reason": "Java fehlt"},
                                                     {"id": "J2", "score": 88, "reason": "React passt"}]}), 900, 100, "f")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Jobs finden").click()
    _run(at)
    assert any(t.value == "Jobs finden" for t in at.title)
    next(t for t in at.text_input if t.label == "Was?").input("Entwickler")
    next(t for t in at.text_input if t.label == "Wo?").input("Köln")
    _btn(at, "Suchen").click()
    _run(at)
    assert seen["what"] == "Entwickler" and seen["where"] == "Köln" and seen["max_age"] == 30
    assert db.get_user_settings(uid)["job_search"]["where"] == "Köln"
    assert any("2 Stellen gefunden" in m.value for m in at.markdown)
    assert any("React" in c.value and "TypeScript" in c.value for c in at.caption)  # Profil-Treffer

    monkeypatch.setitem(llm.PROVIDERS, "fake", fake_ai)
    _btn(at, "KI-Passung prüfen (2 Stellen)").click()
    _run(at)
    assert at.session_state.jobs_ratings["R2"]["score"] == 88
    titles = [m.value for m in at.markdown if m.value.startswith("**") and "(m/w/d)" in m.value]
    assert titles[0].startswith("**Frontend Developer")   # nach Passung sortiert

    next(b for b in at.button if b.key == "apply_R2").click()
    _run(at)
    assert at.session_state.page == "generate"
    assert next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).value == texts["R2"]
    assert at.session_state.gen_url == jobs[1]["url"]


def _three_page_pdf() -> bytes:
    import io
    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(595, 842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _done_state(at):
    s = {"cover_letter": {"subject": "Bewerbung als Frontend Developer", "salutation": "Sehr geehrte Frau Brandt,",
                          "company": "Lumora GmbH", "job_title": "Frontend Developer"}}
    at.session_state["gen"] = {"structured": s, "job_text": "Bewerbung an jobs@lumora.de, Fragen: info@lumora.de",
                               "job_url": "https://example.com/job", "employment_type": "Vollzeit"}
    at.session_state["gen_pdf"] = _three_page_pdf()
    at.session_state["gen_step"] = "done"


def test_send_application_without_mail_account_offers_gmail_draft(env):
    _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _done_state(at)
    _run(at)
    assert next(t for t in at.text_input if t.label == "An").value == "jobs@lumora.de"
    assert "anbei sende ich Ihnen" in next(t for t in at.text_area if t.label == "Text der E-Mail").value
    assert any("E-Mail-Konto verbinden" in b.label for b in at.button)
    draft = next(d for d in at.get("download_button") if d.label.startswith("Entwurf mit Anhang"))
    assert draft.proto.label == "Entwurf mit Anhang (.eml)"     # .eml mit PDF – öffnet in Outlook & Co.


def test_send_application_via_smtp(env, monkeypatch):
    import smtplib
    from tests.test_mailer import FakeSMTP
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    FakeSMTP.fail_login = False
    uid = _user_with_profile()
    db.save_user_settings(uid, {"mail": {"provider": "Gmail", "host": "smtp.gmail.com", "port": 587,
                                         "address": "anna@example.com", "password": "pw"}})
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _done_state(at)
    _run(at)
    _btn(at, "Jetzt senden (von anna@example.com)").click()
    _run(at)
    msg = FakeSMTP.sent[0][1]
    assert msg["To"] == "jobs@lumora.de" and msg["Subject"] == "Bewerbung als Frontend Developer"
    assert next(msg.iter_attachments()).get_filename().endswith(".pdf")
    apps = db.list_applications(uid)
    assert apps[0]["company"] == "Lumora GmbH" and "jobs@lumora.de" in apps[0]["notes"]
    assert any("Gesendet an" in s.value for s in at.success)


def test_settings_mail_account(env, monkeypatch):
    from smartresume import mailer
    tested = []
    monkeypatch.setattr(mailer, "test_account", lambda acc: tested.append(acc))
    uid = _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Einstellungen").click()
    _run(at)
    assert next(t for t in at.text_input if t.label == "Deine E-Mail-Adresse").value == "anna@example.com"
    next(t for t in at.text_input if t.label == "Deine E-Mail-Adresse").input("anna@gmail.com")
    _run(at)                                                   # Anbieter wird an der Adresse erkannt
    assert next(s for s in at.selectbox if s.label == "Anbieter").value == "Gmail"
    next(t for t in at.text_input if t.label.startswith("App-Passwort")).input("abcd efgh ijkl mnop")
    _run(at)
    _btn(at, "Verbindung testen").click()
    _run(at)
    assert tested and tested[0]["host"] == "smtp.gmail.com"
    _btn(at, "Speichern").click()
    _run(at)
    assert db.get_user_settings(uid)["mail"]["password"] == "abcd efgh ijkl mnop"


def _progress_text(at):
    import re as _re
    for el in at.get("progress"):
        m = _re.search(r"Profil zu (\d+) %", str(el.proto))
        if m:
            return int(m.group(1))
    return None


def test_profile_progress_updates_live_and_jumps(env):
    uid = _user_with_profile()
    prof = db.get_profile(uid)["data"]
    prof["personal"].update(first_name="Max", last_name="")   # nur Vorname → Punkt offen
    db.save_profile(uid, data=prof)
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Mein Profil").click()
    _run(at)
    before = _progress_text(at)
    jump = next(b for b in at.button if b.label.startswith("Vor- und Nachname"))
    jump.click()
    _run(at)
    assert at.session_state.profile_tab.endswith("Persönlich")
    assert any("Hier ergänzen" in i.value for i in at.info)
    next(t for t in at.text_input if t.label == "Nachname *").input("Mustermann")
    _run(at)
    after = _progress_text(at)
    assert after > before                     # im selben Durchlauf aktualisiert, nicht erst beim nächsten
    assert not any(b.label.startswith("Vor- und Nachname") for b in at.button)


def test_review_shows_ats_check_and_adds_profile_skill(env, monkeypatch):
    monkeypatch.setitem(FAKE_AI, "keywords", [
        {"term": "Shopify", "profile": "Shopify"}, {"term": "Tailwind CSS", "profile": "Tailwind CSS"},
        {"term": "Vue.js", "profile": ""}, {"term": "Liquid", "profile": "Liquid"}])
    _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=90)))
    next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).input(
        "Frontend Developer (m/w/d) bei Lumora GmbH in Köln. Shopify, Liquid, Tailwind CSS und Vue.js.")
    _btn(at, "Bewerbung erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "review"
    exp = next(e for e in at.expander if "ATS-Check" in e.label)
    assert "25 %" in exp.label and "ehrlich möglich: 75 %" in exp.label     # nur Shopify steht drin
    _btn(at, "In Kenntnisse aufnehmen").click()
    _run(at)
    exp = next(e for e in at.expander if "ATS-Check" in e.label)
    assert "50 %" in exp.label
    assert any("Tailwind CSS" in str(s.get("items")) for s in at.session_state.gen["structured"]["skills"])
    assert not any("Vue.js" in str(s.get("items")) for s in at.session_state.gen["structured"]["skills"])


def test_local_mode_login_with_email_only(env, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_LOCAL", "1")              # so startet SmartResume.exe / starten.bat
    at = _run(AppTest.from_file(APP, default_timeout=60))
    assert not any(t.label == "Code" for t in at.text_input)
    next(t for t in at.text_input if t.label == "Deine E-Mail-Adresse").input("Lena@Example.com")
    _btn(at, "Weiter").click()
    _run(at)
    user = at.session_state.user
    assert user["email"] == "lena@example.com" and user["is_admin"] and not SENT   # kein Code verschickt
    assert db.get_profile(user["id"])["data"]["personal"]["email"] == "lena@example.com"
    import time
    with db.connect() as con:
        expires = con.execute("SELECT expires_at FROM sessions WHERE user_id=?", (user["id"],)).fetchone()[0]
    assert expires - time.time() > 5 * 365 * 24 * 3600         # bleibt angemeldet
    # zweite Person am selben PC bekommt ein eigenes Konto
    at2 = _run(AppTest.from_file(APP, default_timeout=60))
    next(t for t in at2.text_input if t.label == "Deine E-Mail-Adresse").input("tom@example.com")
    _btn(at2, "Weiter").click()
    _run(at2)
    assert at2.session_state.user["id"] != user["id"] and not at2.session_state.user["is_admin"]


def test_local_mode_needs_launch_token(env, monkeypatch):
    """Lokal kommt nur das eigene App-Fenster (mit Start-Token) ins Login – nicht andere Windows-Konten."""
    monkeypatch.setenv("SMARTRESUME_LOCAL", "1")
    monkeypatch.setenv("SMARTRESUME_LOCAL_TOKEN", "geheim-123")
    at = _run(AppTest.from_file(APP, default_timeout=60))
    assert not any(t.label == "Deine E-Mail-Adresse" for t in at.text_input)
    assert any("Startmenü" in i.value for i in at.info)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["k"] = "geheim-123"
    _run(at)
    assert any(t.label == "Deine E-Mail-Adresse" for t in at.text_input)


def test_local_mode_is_single_user_friendly(env, monkeypatch):
    """Lokal (Store-App): keine Admin-/Server-Begriffe, keine Nutzerverwaltung, jedes Konto darf KI einrichten."""
    monkeypatch.setenv("SMARTRESUME_LOCAL", "1")
    at = _run(AppTest.from_file(APP, default_timeout=60))
    assert any("Willkommen" in s.value for s in at.subheader)
    assert not any("Administrator" in m.value for m in at.markdown)
    next(t for t in at.text_input if t.label == "Deine E-Mail-Adresse").input("lena@example.com")
    _btn(at, "Weiter").click()
    _run(at)
    labels = [b.label for b in at.button]
    assert "Verwaltung" not in labels and "KI einrichten" in labels
    at2 = _run(AppTest.from_file(APP, default_timeout=60))   # zweites Konto am selben PC
    next(t for t in at2.text_input if t.label == "Deine E-Mail-Adresse").input("tom@example.com")
    _btn(at2, "Weiter").click()
    _run(at2)
    assert "KI einrichten" in [b.label for b in at2.button]


def test_settings_backup_section(env):
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Einstellungen").click()
    _run(at)
    assert any(s.value == "Daten & Sicherung" for s in at.subheader)
    _btn(at, "Sicherung erstellen").click()
    _run(at)
    assert at.session_state.backup_zip[:2] == b"PK"                 # ZIP liegt zum Herunterladen bereit


def test_info_page_has_privacy_report_and_licenses(env):
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    _btn(at, "Hilfe & Info").click()
    _run(at)
    links = {b.label: b.url for b in at.get("link_button")}
    assert links["Problem melden / Feedback"].startswith("mailto:mail@soufian.me?subject=")
    assert "Unpassenden KI-Inhalt melden" in links
    assert any("Datenschutzerklärung" in e.label for e in at.expander)
    assert any("Affero" in m.value for m in at.markdown)
