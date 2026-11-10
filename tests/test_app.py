"""UI-Tests: die echte app.py wird mit Streamlits AppTest durchgeklickt.
Die KI wird durch einen Fake-Provider ersetzt (schnell, deterministisch, kostenlos)."""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from smartresume import auth, db, llm, render

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
    _btn(at, "👤 Mein Profil").click()
    _run(at)
    name_input = next(t for t in at.text_input if t.label == "Vollständiger Name *")
    assert name_input.value == "Max Mustermann"
    name_input.input("Max M.")
    _run(at)
    _btn(at, "💾 Profil speichern").click()
    _run(at)
    assert db.get_profile(uid)["data"]["personal"]["name"] == "Max M."
    # Station hinzufügen und wieder entfernen
    n = len(db.get_profile(uid)["data"]["experience"])
    _btn(at, "＋ Station hinzufügen").click()
    _run(at)
    assert len(at.session_state.draft["experience"]) == n + 1
    next(b for b in at.button if b.label == "🗑").click()
    _run(at)
    assert len(at.session_state.draft["experience"]) == n


@pytest.mark.skipif(render.find_typst() is None, reason="Typst nicht installiert")
def test_full_generation_flow(env):
    uid = _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=90)))
    job = next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext"))
    job.input("Frontend Developer (m/w/d) bei Lumora GmbH in Köln. Aufgaben: Vue.js, TypeScript, Performance. "
              "Bitte nenne deine Gehaltsvorstellung.")
    next(t for t in at.text_area if t.label.startswith("Zusätzliche Skills")).input("Figma")
    _btn(at, "✨ Bewerbung erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "review", [e.value for e in at.error]
    g = at.session_state.gen
    assert g["structured"]["cover_letter"]["subject"] == "Bewerbung als Frontend Developer"
    assert "39.000–42.000" in g["structured"]["cover_letter"]["p4"]  # deterministisch ergänzt
    assert "Werkstudent" not in env["calls"][0]  # System-Prompt ist statisch
    assert any("Vue.js" in i.value for i in at.info)  # Lücke wird angezeigt
    assert db.user_token_total(uid) == 3800

    _btn(at, "📄 PDF erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "done"
    pdf = at.session_state.gen_pdf
    assert render.count_pages(pdf) == 3
    assert "Lumora GmbH" in render.pdf_text(pdf)[1]

    _btn(at, "✅ Als beworben speichern").click()
    _run(at)
    apps = db.list_applications(uid)
    assert len(apps) == 1 and apps[0]["company"] == "Lumora GmbH" and apps[0]["employment_type"] == "Vollzeit"

    # Tracking-Seite: Status ändern und Bewerbung zum Bearbeiten öffnen
    _btn(at, "📋 Meine Bewerbungen").click()
    _run(at)
    assert any("Lumora GmbH" in e.label for e in at.expander)
    _btn(at, "✏️ Bearbeiten").click()
    _run(at)
    assert at.session_state.page == "generate" and at.session_state.gen_step == "review"
    assert at.session_state.gen_app_id == apps[0]["id"]


def test_daily_limit(env):
    uid = _user_with_profile()
    (env["tmp"] / "branding.json").write_text(json.dumps({"daily_limit_per_user": 1}))
    db.log_usage(uid, "generate", "fake-1", 100)
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).input("Stellenanzeige " * 20)
    _btn(at, "✨ Bewerbung erstellen").click()
    _run(at)
    assert at.session_state.gen_step == "manual"           # Limit erreicht → Abo-Modus statt Abbruch
    assert any("Tageslimit" in i.value for i in at.info)
    assert not env["calls"]


def test_settings_and_admin_pages_render(env):
    db.create_user("chef@example.com", is_admin=True)
    db.create_user("bernd@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "chef@example.com")
    _btn(at, "⚙️ Einstellungen").click()
    _run(at)
    assert any("Einstellungen" in t.value for t in at.title)
    _btn(at, "🛡 Verwaltung").click()
    _run(at)
    assert any("Verwaltung" in t.value for t in at.title)


def test_non_admin_has_no_admin_page(env):
    db.create_user("bernd@example.com")
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)), "bernd@example.com")
    assert not any(b.label == "🛡 Verwaltung" for b in at.button)


# ---------------------------------------------------------------------------
# Abo-Modus (Kopieren & Einfügen über Gemini/ChatGPT)
# ---------------------------------------------------------------------------
JOB = ("Frontend Developer (m/w/d) bei Lumora GmbH in Köln. Aufgaben: Vue.js, TypeScript, Performance. "
       "Bitte nenne deine Gehaltsvorstellung.")


def _start_generation(at):
    next(t for t in at.text_area if t.label.startswith("… oder Anzeigentext")).input(JOB)
    _btn(at, "✨ Bewerbung erstellen").click()
    return _run(at)


def _paste_answer(at, text):
    next(t for t in at.text_area if t.label.startswith("Antwort von Gemini")).input(text)
    _btn(at, "Weiter").click()
    return _run(at)


def test_without_api_key_uses_chat_mode(env, monkeypatch):
    monkeypatch.delenv("FAKE_KEY")                      # keine KI-API eingerichtet
    _user_with_profile()
    at = _login(_run(AppTest.from_file(APP, default_timeout=60)))
    assert any("Keine KI-API eingerichtet" in i.value for i in at.info)
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
    _btn(at, "👤 Mein Profil").click()
    _run(at)
    _btn(at, "🔁 Gespeicherten CV erneut auslesen").click()
    _run(at)
    assert "Verkäuferin" in next(c.value for c in at.code)
    answer = {"personal": {"name": "Anna Beispiel", "zip_city": "Köln"},
              "experience": [{"company": "Muster AG", "role": "Verkäuferin", "start": "2020", "end": "2024",
                              "bullets": ["Beratung von Kundinnen und Kunden"]}]}
    _paste_answer(at, json.dumps(answer, ensure_ascii=False))
    prof = db.get_profile(uid)["data"]
    assert prof["personal"]["name"] == "Anna Beispiel" and prof["experience"][0]["company"] == "Muster AG"
