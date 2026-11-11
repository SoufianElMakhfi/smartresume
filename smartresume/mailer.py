"""Bewerbungen per E-Mail versenden – aus dem eigenen Postfach des Nutzers.

Drei Wege:
1. Direkt aus der App per SMTP mit (App-)Passwort (Gmail, GMX, WEB.DE, T-Online, iCloud …). Der Anbieter wird
   an der Adresse erkannt. Die Zugangsdaten liegen nur lokal in den Nutzereinstellungen (data/smartresume.db).
2. Ohne Einrichtung: „Entwurf mit Anhang“ – eine .eml-Datei, die sich im Mailprogramm (Outlook, Thunderbird,
   Apple Mail) als fertige E-Mail mit PDF öffnet.
3. Ohne Einrichtung: Gmail-Entwurf im Browser (Empfänger, Betreff, Text vorausgefüllt; PDF selbst anhängen).

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
    "Gmail": {"host": "smtp.gmail.com", "port": 587, "domains": ("gmail.com", "googlemail.com"),
              "help_url": "https://myaccount.google.com/apppasswords", "help_label": "App-Passwort erstellen",
              "how": "1. Bei Google muss die **Bestätigung in zwei Schritten** aktiv sein.\n"
                     "2. Auf **App-Passwort erstellen** klicken, einen Namen eingeben (z. B. SmartResume) und "
                     "auf „Erstellen“ klicken.\n"
                     "3. Das 16-stellige Passwort unten einfügen. Dein normales Google-Passwort funktioniert "
                     "hier nicht.",
              "password_label": "App-Passwort (16 Buchstaben)", "saves_sent": True},
    "GMX": {"host": "mail.gmx.net", "port": 587, "domains": ("gmx.de", "gmx.net", "gmx.at", "gmx.ch"),
            "help_url": "https://www.gmx.net/", "help_label": "GMX öffnen",
            "how": "1. Bei GMX einloggen: **E-Mail → Einstellungen → POP3/IMAP Abruf**.\n"
                   "2. Den Haken bei **„Senden und Empfangen von E-Mails via externem Programm“** setzen und "
                   "speichern.\n"
                   "3. Unten dein GMX-Passwort eingeben (bei aktiver Zwei-Faktor-Anmeldung ein App-Passwort).",
            "password_label": "GMX-Passwort", "saves_sent": False},
    "WEB.DE": {"host": "smtp.web.de", "port": 587, "domains": ("web.de",),
               "help_url": "https://web.de/", "help_label": "WEB.DE öffnen",
               "how": "1. Bei WEB.DE einloggen: **E-Mail → Einstellungen → POP3/IMAP Abruf**.\n"
                      "2. Den Haken bei **„Senden und Empfangen von E-Mails via externem Programm“** setzen und "
                      "speichern.\n"
                      "3. Unten dein WEB.DE-Passwort eingeben (bei aktiver Zwei-Faktor-Anmeldung ein "
                      "App-Passwort).",
               "password_label": "WEB.DE-Passwort", "saves_sent": False},
    "T-Online": {"host": "securesmtp.t-online.de", "port": 587, "domains": ("t-online.de", "magenta.de"),
                 "help_url": "https://email.t-online.de/", "help_label": "T-Online E-Mail öffnen",
                 "how": "1. Im E-Mail Center von T-Online: **Einstellungen → Passwörter → Passwort für "
                        "E-Mail-Programme** festlegen.\n"
                        "2. Dieses Passwort unten eingeben (nicht dein normales Telekom-Login-Passwort).",
                 "password_label": "Passwort für E-Mail-Programme", "saves_sent": False},
    "iCloud": {"host": "smtp.mail.me.com", "port": 587, "domains": ("icloud.com", "me.com", "mac.com"),
               "help_url": "https://account.apple.com/", "help_label": "Apple-Account öffnen",
               "how": "1. Im Apple-Account: **Anmelden und Sicherheit → App-spezifische Passwörter** → neues "
                      "Passwort erstellen (Name z. B. SmartResume).\n"
                      "2. Das Passwort (Format xxxx-xxxx-xxxx-xxxx) unten einfügen.",
               "password_label": "App-spezifisches Passwort", "saves_sent": False},
    "Yahoo": {"host": "smtp.mail.yahoo.com", "port": 587, "domains": ("yahoo.com", "yahoo.de", "ymail.com"),
              "help_url": "https://login.yahoo.com/account/security", "help_label": "Yahoo-Sicherheit öffnen",
              "how": "1. In den Yahoo-Kontoeinstellungen unter **Kontosicherheit → App-Passwort generieren** ein "
                     "Passwort erstellen.\n"
                     "2. Das Passwort unten einfügen.",
              "password_label": "App-Passwort", "saves_sent": False},
    "Posteo": {"host": "posteo.de", "port": 587, "domains": ("posteo.de", "posteo.net"),
               "help_url": "", "help_label": "",
               "how": "Unten einfach dein Posteo-Passwort eingeben – es ist nichts weiter einzurichten.",
               "password_label": "Posteo-Passwort", "saves_sent": False},
    "mailbox.org": {"host": "smtp.mailbox.org", "port": 587, "domains": ("mailbox.org",),
                    "help_url": "", "help_label": "",
                    "how": "Unten dein mailbox.org-Passwort eingeben (bei Zwei-Faktor-Anmeldung ein "
                           "App-Passwort).",
                    "password_label": "Passwort", "saves_sent": False},
    "freenet": {"host": "mx.freenet.de", "port": 587, "domains": ("freenet.de",),
                "help_url": "https://email.freenet.de/", "help_label": "freenet Mail öffnen",
                "how": "1. In freenet Mail unter **Einstellungen → POP3/IMAP/SMTP** den Zugriff über externe "
                       "Programme aktivieren.\n"
                       "2. Unten dein freenet-Passwort eingeben.",
                "password_label": "freenet-Passwort", "saves_sent": False},
    "Outlook / Hotmail": {"host": "", "port": 587, "unsupported": True,
                          "domains": ("outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com",
                                      "live.de", "msn.com"),
                          "help_url": "", "help_label": "",
                          "how": "Microsoft lässt bei privaten Outlook-, Hotmail- und Live-Adressen den Versand aus "
                                 "anderen Programmen nicht mehr per Passwort zu. Nutze deshalb bei der fertigen "
                                 "Bewerbung **„Entwurf mit Anhang“**: Die Datei öffnet sich in Outlook als fertige "
                                 "E-Mail mit PDF – du klickst nur noch auf Senden.",
                          "password_label": "", "saves_sent": True},
    "Andere": {"host": "", "port": 587, "domains": (), "help_url": "", "help_label": "",
               "how": "SMTP-Server und Port findest du in der Hilfe deines E-Mail-Anbieters (Stichwort „SMTP“ "
                      "oder „E-Mail-Programm einrichten“).",
               "password_label": "Passwort", "saves_sent": False},
}


def detect_provider(address: str) -> str:
    """Anbieter anhand der Adresse („max@gmx.de“ → „GMX“); unbekannt → „Andere“."""
    domain = (address or "").strip().lower().rsplit("@", 1)[-1]
    return next((name for name, p in PROVIDERS.items() if domain in p["domains"]), "Andere")


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
    # Immer förmlich: „Sehr geehrte Frau/Herr X“ nur, wenn die Anzeige eine Ansprechperson nennt –
    # sonst (auch statt „Hallo …“) „Sehr geehrte Damen und Herren“.
    salutation = (cl.get("salutation") or "").strip()
    if not salutation.startswith("Sehr geehrte"):
        salutation = "Sehr geehrte Damen und Herren,"
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


def build_message(acc: dict, sender_name: str, to: str, subject: str, body: str,
                  attachments: list[tuple[bytes, str]], copy_to_self: bool = False) -> EmailMessage:
    """attachments: [(pdf_bytes, dateiname)] – eine Bewerbungsmappe oder Anschreiben + Lebenslauf getrennt."""
    if not valid_email(to):
        raise MailError("Bitte eine gültige Empfängeradresse angeben.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, acc["address"])) if sender_name else acc["address"]
    msg["To"] = to.strip()
    if copy_to_self:
        msg["Bcc"] = acc["address"]
    msg.set_content(body)
    for data, filename in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    return msg


def build_draft(sender_name: str, sender_address: str, to: str, subject: str, body: str,
                attachments: list[tuple[bytes, str]]) -> bytes:
    """E-Mail-Entwurf als .eml-Datei: öffnet sich im Mailprogramm als neue, noch nicht gesendete Nachricht
    mit allen Anhängen (X-Unsent). Empfänger darf leer sein."""
    msg = EmailMessage()
    msg["X-Unsent"] = "1"
    msg["Subject"] = subject
    if sender_address:
        msg["From"] = formataddr((sender_name, sender_address)) if sender_name else sender_address
    if valid_email(to):
        msg["To"] = to.strip()
    msg.set_content(body)
    for data, filename in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    return msg.as_bytes()


def _connect(acc: dict):
    host, port = acc["host"], int(acc.get("port") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())
        pw = acc["password"].replace(" ", "") if "gmail" in host else acc["password"]
        server.ehlo()
        if "plain" in server.esmtp_features.get("auth", "").lower().split():
            # Nur PLAIN versuchen: smtplib.login() probiert nach einer Ablehnung noch LOGIN – Gmail trennt dann
            # die Verbindung, und statt „Passwort falsch“ käme nur „SMTPServerDisconnected“ an.
            server.user, server.password = acc["address"], pw
            server.auth("PLAIN", server.auth_plain)
        else:
            server.login(acc["address"], pw)
        return server
    except smtplib.SMTPAuthenticationError as e:
        if "gmail" in host:
            n = len(acc["password"].replace(" ", ""))
            raise MailError("Gmail hat die Anmeldung abgelehnt („Username and Password not accepted“). Hier "
                            "funktioniert nur ein **App-Passwort** (16 Buchstaben), nicht dein normales "
                            "Google-Passwort" + (f" – eingegeben wurden {n} Zeichen" if n != 16 else "") +
                            ". Bestätigung in zwei Schritten muss aktiv sein.") from e
        raise MailError("Anmeldung beim E-Mail-Anbieter fehlgeschlagen – Adresse oder Passwort stimmt nicht.") from e
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
