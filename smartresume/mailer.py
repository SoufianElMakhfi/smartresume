"""Bewerbungen per E-Mail versenden – aus dem eigenen Postfach des Nutzers.

Zwei Wege:
1. Ohne Einrichtung: Gmail-Entwurf bzw. Mailprogramm öffnen (Empfänger, Betreff, Text vorausgefüllt);
   das PDF hängt der Nutzer selbst an.
2. Direkt aus der App per SMTP mit App-Passwort (Gmail, GMX, WEB.DE …). Die Zugangsdaten liegen nur lokal
   in den Nutzereinstellungen (data/smartresume.db).

Die Empfängeradresse kommt aus dem Anzeigentext – die Jobbörsen geben Kontaktdaten nicht heraus.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote, urlencode

PROVIDERS = {
    "Gmail": {"host": "smtp.gmail.com", "port": 587, "help_url": "https://myaccount.google.com/apppasswords",
              "how": "Bei Google muss die **Bestätigung in zwei Schritten** aktiv sein. Dann unter „App-Passwörter“ "
                     "einen Namen eingeben (z. B. SmartResume) → „Erstellen“ → das 16-stellige Passwort hier "
                     "einfügen. Dein normales Google-Passwort funktioniert hier nicht.",
              "saves_sent": True},
    "GMX": {"host": "mail.gmx.net", "port": 587, "help_url": "https://www.gmx.net/",
            "how": "Bei GMX unter E-Mail → Einstellungen → „POP3/IMAP Abruf“ den Haken bei „Senden und Empfangen "
                   "von E-Mails via externem Programm“ setzen. Dann hier dein GMX-Passwort eingeben (bei aktiver "
                   "Zwei-Faktor-Anmeldung ein App-Passwort).",
            "saves_sent": False},
    "WEB.DE": {"host": "smtp.web.de", "port": 587, "help_url": "https://web.de/",
               "how": "Bei WEB.DE unter E-Mail → Einstellungen → „POP3/IMAP Abruf“ den Haken bei „Senden und "
                      "Empfangen von E-Mails via externem Programm“ setzen. Dann hier dein WEB.DE-Passwort eingeben "
                      "(bei aktiver Zwei-Faktor-Anmeldung ein App-Passwort).",
               "saves_sent": False},
    "Andere": {"host": "", "port": 587, "help_url": "",
               "how": "SMTP-Server und Port findest du in der Hilfe deines E-Mail-Anbieters.", "saves_sent": False},
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
_GOOD = ("bewerb", "karriere", "career", "jobs", "job", "recruit", "personal", "hr", "talent", "people")
_BAD = ("noreply", "no-reply", "datenschutz", "privacy", "dsb", "info@arbeitsagentur", "support", "newsletter",
        "abuse", "webmaster")


class MailError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Empfänger, Betreff, Text
# ---------------------------------------------------------------------------
def find_emails(text: str) -> list[str]:
    """E-Mail-Adressen aus dem Anzeigentext, die wahrscheinlichste Bewerbungsadresse zuerst."""
    found: list[str] = []
    for m in EMAIL_RE.finditer(text or ""):
        e = m.group(0).strip(".").lower()
        if e not in found and not e.endswith((".png", ".jpg", ".gif")):
            found.append(e)

    def rank(e: str) -> tuple:
        local = e.split("@")[0]
        bad = any(b in e for b in _BAD)
        good = any(g in local for g in _GOOD)
        return (bad, not good)
    return sorted(found, key=rank)   # stabil: bei Gleichstand Reihenfolge in der Anzeige


def valid_email(e: str) -> bool:
    return bool(EMAIL_RE.fullmatch((e or "").strip()))


def default_subject(structured: dict) -> str:
    return (structured.get("cover_letter") or {}).get("subject") or "Bewerbung"


def default_body(structured: dict, profile: dict) -> str:
    cl = structured.get("cover_letter") or {}
    p = profile.get("personal") or {}
    salutation = cl.get("salutation") or "Sehr geehrte Damen und Herren,"
    title = cl.get("job_title") or (structured.get("job") or {}).get("job_title") or ""
    stelle = f" für die Stelle als {title}" if title else ""
    sign = "\n".join(x for x in (p.get("name", ""), p.get("phone", ""), p.get("email", "")) if x)
    return (f"{salutation}\n\n"
            f"anbei sende ich Ihnen meine Bewerbungsunterlagen{stelle}. Im Anhang finden Sie Anschreiben und "
            f"Lebenslauf als PDF.\n\n"
            f"Über eine Einladung zu einem persönlichen Gespräch freue ich mich sehr.\n\n"
            f"Mit freundlichen Grüßen\n{sign}")


def gmail_compose_url(to: str, subject: str, body: str) -> str:
    return "https://mail.google.com/mail/?" + urlencode({"view": "cm", "fs": 1, "to": to, "su": subject,
                                                         "body": body})


def mailto_url(to: str, subject: str, body: str) -> str:
    return f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"


# ---------------------------------------------------------------------------
# Versand per SMTP
# ---------------------------------------------------------------------------
def account_ready(acc: dict | None) -> bool:
    return bool(acc and acc.get("host") and acc.get("address") and acc.get("password"))


def build_message(acc: dict, sender_name: str, to: str, subject: str, body: str, pdf: bytes, filename: str,
                  copy_to_self: bool = False) -> EmailMessage:
    if not valid_email(to):
        raise MailError("Bitte eine gültige Empfängeradresse angeben.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, acc["address"])) if sender_name else acc["address"]
    msg["To"] = to.strip()
    if copy_to_self:
        msg["Bcc"] = acc["address"]
    msg.set_content(body)
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return msg


def _connect(acc: dict):
    host, port = acc["host"], int(acc.get("port") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())
        server.login(acc["address"], acc["password"].replace(" ", "") if "gmail" in host else acc["password"])
        return server
    except smtplib.SMTPAuthenticationError as e:
        raise MailError("Anmeldung beim E-Mail-Anbieter fehlgeschlagen – Adresse oder (App-)Passwort stimmt nicht. "
                        "Bei Gmail brauchst du ein App-Passwort, nicht dein normales Passwort.") from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Keine Verbindung zum Mailserver {host}:{port} ({e.__class__.__name__}).") from e


def test_account(acc: dict) -> None:
    """Meldet sich nur an (sendet nichts). Wirft MailError bei Problemen."""
    with _connect(acc):
        pass


def send(acc: dict, msg: EmailMessage) -> None:
    server = _connect(acc)
    try:
        with server:
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Die E-Mail konnte nicht gesendet werden ({e.__class__.__name__}: {e}).") from e
