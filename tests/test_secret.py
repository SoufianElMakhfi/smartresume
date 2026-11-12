import sys

import pytest

from smartresume import config, db, paths, secret

win_only = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI gibt es nur unter Windows")


@win_only
def test_roundtrip_and_plaintext_passthrough():
    enc = secret.protect("sk-geheim-äöü")
    assert enc.startswith("dpapi:") and "geheim" not in enc
    assert secret.reveal(enc) == "sk-geheim-äöü"
    assert secret.protect(enc) == enc                       # nicht doppelt verschlüsseln
    assert secret.reveal("alter-klartext") == "alter-klartext"
    assert secret.reveal("dpapi:kaputt") == ""              # fremder PC/kaputt → leer statt Absturz
    assert secret.protect("") == ""


def test_secret_names():
    assert secret.is_secret_name("GEMINI_API_KEY") and secret.is_secret_name("SMTP_PASSWORD")
    assert not secret.is_secret_name("SMTP_HOST") and not secret.is_secret_name("SMARTRESUME_URL")


@win_only
def test_env_file_is_encrypted_and_migrated(tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTRESUME_HOME", str(tmp_path))
    monkeypatch.setattr(config, "_from_file", set())
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    env = paths.env_file()
    env.write_text("# Kommentar\nGEMINI_API_KEY=AIza-alt\nSMTP_HOST=smtp.example.com\n", encoding="utf-8")
    config.load_env()
    import os
    assert os.environ["GEMINI_API_KEY"] == "AIza-alt"
    text = env.read_text(encoding="utf-8")
    assert "AIza-alt" not in text and "GEMINI_API_KEY=dpapi:" in text   # Klartext wurde verschlüsselt
    assert "SMTP_HOST=smtp.example.com" in text and "# Kommentar" in text
    config.save_values({"GROQ_API_KEY": "gsk-neu"})
    assert "gsk-neu" not in env.read_text(encoding="utf-8") and os.environ["GROQ_API_KEY"] == "gsk-neu"


@win_only
def test_mail_password_encrypted_in_db(tmp_db):
    uid = db.create_user("a@example.com")
    db.save_user_settings(uid, {"mail": {"address": "a@example.com", "password": "pw-123"}})
    with db.connect() as con:
        raw = con.execute("SELECT settings FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert "pw-123" not in raw and "dpapi:" in raw
    assert db.get_user_settings(uid)["mail"]["password"] == "pw-123"


@win_only
def test_old_plaintext_mail_password_is_migrated(tmp_db):
    import json
    uid = db.create_user("b@example.com")
    with db.connect() as con:
        con.execute("UPDATE users SET settings=? WHERE id=?",
                    (json.dumps({"mail": {"password": "alt-klar"}}), uid))
    db.init_db()
    with db.connect() as con:
        raw = con.execute("SELECT settings FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert "alt-klar" not in raw
    assert db.get_user_settings(uid)["mail"]["password"] == "alt-klar"
