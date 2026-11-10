import time

import pytest

from smartresume import auth, db


def test_code_roundtrip(tmp_db):
    code = auth.request_code("Anna@Example.com")
    assert len(code) == 6 and code.isdigit()
    with db.connect() as con:
        stored = con.execute("SELECT code_hash FROM login_codes").fetchone()[0]
    assert code not in stored                                   # nur Hash gespeichert
    assert auth.verify_code("anna@example.com", f" {code[:3]} {code[3:]} ")  # Leerzeichen egal
    with pytest.raises(auth.AuthError):                        # Code ist verbraucht
        auth.verify_code("anna@example.com", code)


def test_wrong_codes_lock_after_max_attempts(tmp_db):
    code = auth.request_code("anna@example.com")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(auth.MAX_ATTEMPTS):
        assert auth.verify_code("anna@example.com", wrong) is False
    with pytest.raises(auth.AuthError, match="Fehlversuche"):
        auth.verify_code("anna@example.com", code)               # auch der richtige zählt nicht mehr


def test_code_expires_and_resend_throttle(tmp_db, monkeypatch):
    t = [1_000_000.0]
    monkeypatch.setattr(auth.time, "time", lambda: t[0])
    code = auth.request_code("anna@example.com")
    with pytest.raises(auth.AuthError, match="warten"):
        auth.request_code("anna@example.com")
    t[0] += auth.CODE_TTL + 1
    with pytest.raises(auth.AuthError, match="abgelaufen"):
        auth.verify_code("anna@example.com", code)
    assert auth.request_code("anna@example.com")               # danach geht's wieder
    auth.discard_code("anna@example.com")
    assert auth.request_code("anna@example.com")               # verworfen → sofort neu möglich


def test_invalid_email_and_unknown_code(tmp_db):
    with pytest.raises(db.UserError):
        auth.request_code("keine-mail")
    assert auth.verify_code("keine-mail", "123456") is False
    with pytest.raises(auth.AuthError):
        auth.verify_code("niemand@example.com", "123456")


def test_sessions(tmp_db, monkeypatch):
    uid = db.create_user("anna@example.com")
    tok = auth.create_session(uid)
    assert auth.user_from_session(tok)["id"] == uid
    assert auth.user_from_session("falsch") is None and auth.user_from_session("") is None
    auth.end_session(tok)
    assert auth.user_from_session(tok) is None
    t1, t2 = auth.create_session(uid), auth.create_session(uid)
    auth.end_all_sessions(uid)
    assert auth.user_from_session(t1) is None and auth.user_from_session(t2) is None
    tok = auth.create_session(uid)
    real = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: real + auth.SESSION_TTL + 1)
    assert auth.user_from_session(tok) is None                 # abgelaufen


def test_send_without_smtp_prints_code(monkeypatch, capsys):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert auth.send_code("a@example.com", "123456", "SmartResume", "http://localhost:8501/?x") is False
    assert "123456" in capsys.readouterr().out


def test_send_via_smtp(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = (host, port)
        def starttls(self, context=None): sent["tls"] = True
        def login(self, u, p): sent["login"] = (u, p)
        def send_message(self, msg): sent["msg"] = msg
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(auth.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    link = auth.login_link("http://localhost:8501/", "a@example.com", "654321")
    assert link == "http://localhost:8501/?email=a%40example.com&code=654321"
    assert auth.send_code("a@example.com", "654321", "JobBoost", link) is True
    msg = sent["msg"]
    assert sent["host"] == ("smtp.example.com", 587) and sent["tls"] and sent["login"] == ("bot@example.com", "pw")
    assert msg["Subject"].startswith("654321") and msg["To"] == "a@example.com" and msg["From"] == "bot@example.com"
    assert link in msg.get_body(("plain",)).get_content()
