import smtplib
from urllib.parse import parse_qs, urlparse

import pytest

from smartresume import mailer

ACC = {"provider": "Gmail", "host": "smtp.gmail.com", "port": 587, "address": "max@example.com",
       "password": "abcd efgh ijkl mnop"}


def test_find_emails_prefers_application_address():
    text = ("Fragen? info@firma.de. Datenschutz: datenschutz@firma.de\n"
            "Bewerbung bitte an: Bewerbung@Firma.de. Logo: bild@2x.png")
    assert mailer.find_emails(text) == ["bewerbung@firma.de", "info@firma.de", "datenschutz@firma.de"]
    assert mailer.find_emails("Keine Adresse") == []


def test_default_texts():
    s = {"cover_letter": {"subject": "Bewerbung als Entwickler", "salutation": "Sehr geehrte Frau Brandt,",
                          "job_title": "Entwickler"}}
    prof = {"personal": {"name": "Max Mustermann", "phone": "0170 123", "email": "max@example.com"}}
    assert mailer.default_subject(s) == "Bewerbung als Entwickler"
    body = mailer.default_body(s, prof)
    assert body.startswith("Sehr geehrte Frau Brandt,\n\nanbei sende ich Ihnen meine Bewerbungsunterlagen "
                           "für die Stelle als Entwickler.")
    assert body.endswith("Mit freundlichen Grüßen\nMax Mustermann\n0170 123\nmax@example.com")


def test_compose_urls():
    q = parse_qs(urlparse(mailer.gmail_compose_url("a@b.de", "Bewerbung & mehr", "Zeile 1\nZeile 2")).query)
    assert q["to"] == ["a@b.de"] and q["su"] == ["Bewerbung & mehr"] and q["body"] == ["Zeile 1\nZeile 2"]
    assert mailer.mailto_url("a@b.de", "Hi du", "x").startswith("mailto:a%40b.de?subject=Hi%20du&body=x")


def test_build_message():
    msg = mailer.build_message(ACC, "Max Mustermann", "hr@firma.de", "Bewerbung", "Text",
                               [(b"%PDF-1.7 A", "Anschreiben.pdf"), (b"%PDF-1.7 L", "Lebenslauf.pdf")],
                               copy_to_self=True)
    assert msg["From"] == "Max Mustermann <max@example.com>" and msg["Bcc"] == "max@example.com"
    att = list(msg.iter_attachments())
    assert [a.get_filename() for a in att] == ["Anschreiben.pdf", "Lebenslauf.pdf"]
    assert att[1].get_content() == b"%PDF-1.7 L"
    with pytest.raises(mailer.MailError, match="Empfängeradresse"):
        mailer.build_message(ACC, "", "kein-mail", "B", "T", [(b"", "a.pdf")])


class FakeSMTP:
    sent = []
    fail_login = False
    esmtp_features: dict = {}

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.login_pw = pw

    def send_message(self, msg):
        FakeSMTP.sent.append((self.login_pw, msg))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_and_errors(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent.clear()
    FakeSMTP.fail_login = False
    mailer.send(ACC, mailer.build_message(ACC, "", "hr@firma.de", "B", "T", [(b"%PDF", "a.pdf")]))
    assert FakeSMTP.sent[0][0] == "abcdefghijklmnop"   # Leerzeichen aus Gmail-App-Passwort entfernt
    mailer.test_account(ACC)
    FakeSMTP.fail_login = True
    with pytest.raises(mailer.MailError, match="App-Passwort"):
        mailer.test_account(ACC)
    assert mailer.account_ready(ACC) and not mailer.account_ready({**ACC, "password": ""})


def test_body_is_always_formal():
    prof = {"personal": {"name": "Max Mustermann"}}
    for sal in ("Hallo Max,", "Liebe Anna,", "", None):
        body = mailer.default_body({"cover_letter": {"salutation": sal}}, prof)
        assert body.startswith("Sehr geehrte Damen und Herren,\n\nanbei")
        assert body.endswith("Mit freundlichen Grüßen\nMax Mustermann")


def test_gmail_rejection_is_explained(monkeypatch):
    class Rejecting(FakeSMTP):
        esmtp_features = {"auth": "LOGIN PLAIN XOAUTH2"}

        def ehlo(self):
            pass

        auth_plain = None

        def auth(self, mech, fn):
            assert mech == "PLAIN"      # kein zweiter Versuch mit LOGIN (Gmail trennt sonst die Verbindung)
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")
    monkeypatch.setattr(smtplib, "SMTP", Rejecting)
    with pytest.raises(mailer.MailError, match="App-Passwort.*14 Zeichen"):
        mailer.test_account({**ACC, "password": "normalesPW1234"})


def test_detect_provider():
    assert mailer.detect_provider("Max@GMX.de ") == "GMX"
    assert mailer.detect_provider("max@googlemail.com") == "Gmail"
    assert mailer.detect_provider("max@t-online.de") == "T-Online"
    assert mailer.detect_provider("max@hotmail.de") == "Outlook / Hotmail"
    assert mailer.PROVIDERS["Outlook / Hotmail"]["unsupported"]
    assert mailer.detect_provider("max@firma.de") == mailer.detect_provider("") == "Andere"
    for name, p in mailer.PROVIDERS.items():                 # jeder nutzbare Anbieter hat Server und Anleitung
        assert p["how"] and (p.get("unsupported") or name == "Andere" or p["host"]), name


def test_build_draft_opens_as_unsent_mail_with_attachments():
    import email
    import email.policy
    raw = mailer.build_draft("Max Mustermann", "max@example.com", "jobs@firma.de", "Bewerbung als Entwickler",
                             "Sehr geehrte Damen und Herren,", [(b"%PDF-1", "Anschreiben.pdf"),
                                                               (b"%PDF-2", "Lebenslauf.pdf")])
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    assert msg["X-Unsent"] == "1" and msg["To"] == "jobs@firma.de" and "Max Mustermann" in msg["From"]
    names = [part.get_filename() for part in msg.iter_attachments()]
    assert names == ["Anschreiben.pdf", "Lebenslauf.pdf"]
    no_to = email.message_from_bytes(mailer.build_draft("", "", "", "Betreff", "Text", []))
    assert no_to["To"] is None and no_to["From"] is None              # Empfänger darf noch fehlen
