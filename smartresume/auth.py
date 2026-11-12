"""Login ohne Passwort: E-Mail eingeben → 6-stelligen Code bekommen → eingeloggt.

- Codes: 10 Minuten gültig, max. 5 Fehlversuche, neuer Code frühestens nach 30 s.
  In der DB liegt nur ein Hash, nie der Code selbst.
- Versand per SMTP (Variablen in .env, siehe .env.example). Ohne SMTP wird der Code in
  der Konsole ausgegeben – bei lokalem Betrieb zeigt die App ihn zusätzlich direkt an.
- Sitzungen: zufälliges Token (Cookie im Browser, Hash in der DB), 30 Tage gültig –
  so bleibt man auch nach dem Neuladen der Seite angemeldet.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlencode

from . import db

CODE_TTL = 10 * 60
RESEND_AFTER = 30
MAX_ATTEMPTS = 5
SESSION_TTL = 30 * 24 * 3600
LOCAL_SESSION_TTL = 10 * 365 * 24 * 3600     # lokal: angemeldet bleiben, bis man sich abmeldet


class AuthError(ValueError):
    pass


def _hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def _digits(code: str) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())


# ---------------------------------------------------------------------------
# Einmal-Codes
# ---------------------------------------------------------------------------
def request_code(email: str, path=None) -> str:
    """Erzeugt einen neuen Code für die E-Mail und gibt ihn (im Klartext) zurück."""
    email = db.normalize_email(email)
    now = time.time()
    with db.connect(path) as con:
        row = con.execute("SELECT sent_at FROM login_codes WHERE email=?", (email,)).fetchone()
        if row and now - row["sent_at"] < RESEND_AFTER:
            wait = int(RESEND_AFTER - (now - row["sent_at"])) + 1
            raise AuthError(f"Bitte {wait} Sekunden warten, bevor ein neuer Code angefordert wird.")
        code = f"{secrets.randbelow(1_000_000):06d}"
        con.execute("INSERT OR REPLACE INTO login_codes (email, code_hash, expires_at, sent_at, attempts) "
                    "VALUES (?,?,?,?,0)", (email, _hash(email, code), now + CODE_TTL, now))
    return code


def discard_code(email: str, path=None) -> None:
    """Code verwerfen (z. B. wenn der Versand fehlschlug), damit sofort ein neuer angefordert werden kann."""
    with db.connect(path) as con:
        con.execute("DELETE FROM login_codes WHERE email=?", (email.strip().lower(),))


def verify_code(email: str, code: str, path=None) -> bool:
    """Prüft den Code. Bei Erfolg wird er verbraucht. Wirft AuthError bei Ablauf/zu vielen Versuchen."""
    try:
        email = db.normalize_email(email)
    except db.UserError:
        return False
    code = _digits(code)
    with db.connect(path) as con:
        row = con.execute("SELECT * FROM login_codes WHERE email=?", (email,)).fetchone()
        if not row:
            raise AuthError("Kein gültiger Code vorhanden – bitte einen neuen anfordern.")
        if time.time() > row["expires_at"]:
            con.execute("DELETE FROM login_codes WHERE email=?", (email,))
            raise AuthError("Der Code ist abgelaufen – bitte einen neuen anfordern.")
        if row["attempts"] >= MAX_ATTEMPTS:
            con.execute("DELETE FROM login_codes WHERE email=?", (email,))
            raise AuthError("Zu viele Fehlversuche – bitte einen neuen Code anfordern.")
        if secrets.compare_digest(row["code_hash"], _hash(email, code)):
            con.execute("DELETE FROM login_codes WHERE email=?", (email,))
            return True
        con.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE email=?", (email,))
        return False


# ---------------------------------------------------------------------------
# Versand
# ---------------------------------------------------------------------------
def local_mode() -> bool:
    """Lokaler Betrieb (SmartResume.exe bzw. „SmartResume starten.bat“): Der Launcher bindet die App an
    127.0.0.1 und setzt SMARTRESUME_LOCAL=1. Dann reicht zum Anmelden die E-Mail-Adresse – ohne Code, denn nur
    wer an diesem PC sitzt, erreicht die App. Auf einem Server (ohne den Launcher) bleibt der Code Pflicht."""
    return os.environ.get("SMARTRESUME_LOCAL") == "1"


def local_access_ok(given: str) -> bool:
    """Lokal: Der Launcher erzeugt bei jedem Start ein geheimes Token und öffnet die App mit ?k=<token>.
    Nur wer es kennt (das eigene App-Fenster), darf sich anmelden – nicht andere Windows-Konten auf demselben PC
    und keine Webseite, die 127.0.0.1 anspricht. Ohne Token (z. B. `streamlit run`) keine Prüfung."""
    expected = os.environ.get("SMARTRESUME_LOCAL_TOKEN", "")
    return not expected or secrets.compare_digest(str(given or "").encode(), expected.encode())


def can_configure_ai(user: dict | None) -> bool:
    """KI-Keys einrichten: auf dem Server nur Admins, lokal jedes Konto (es ist ja der eigene PC)."""
    return bool(user) and (bool(user.get("is_admin")) or local_mode())


def session_ttl() -> int:
    return LOCAL_SESSION_TTL if local_mode() else SESSION_TTL


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def login_link(base_url: str, email: str, code: str) -> str:
    if not base_url:
        return ""
    return f"{base_url.rstrip('/')}/?{urlencode({'email': email, 'code': code})}"


def send_code(email: str, code: str, app_name: str = "SmartResume", link: str = "") -> bool:
    """Schickt den Code per Mail. Gibt False zurück, wenn kein SMTP eingerichtet ist
    (dann steht der Code nur in der Konsole)."""
    if not smtp_configured():
        print(f"[{app_name}] Login-Code für {email}: {code}" + (f"  ({link})" if link else ""), flush=True)
        return False

    msg = EmailMessage()
    msg["Subject"] = f"{code} ist dein {app_name}-Code"   # Code im Betreff → steht direkt in der Benachrichtigung
    msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
    msg["To"] = email
    link_txt = f"\nOder direkt anmelden:\n{link}\n" if link else ""
    msg.set_content(f"Dein Anmeldecode für {app_name}:\n\n    {code}\n\n"
                    f"Er ist 10 Minuten gültig.{link_txt}\n"
                    "Du hast keinen Code angefordert? Dann ignoriere diese E-Mail einfach.")
    link_html = (f'<p><a href="{link}" style="display:inline-block;padding:10px 18px;background:#0F5F6E;'
                 f'color:#fff;border-radius:6px;text-decoration:none">Direkt anmelden</a></p>') if link else ""
    msg.add_alternative(
        f'<div style="font-family:system-ui,sans-serif;max-width:420px">'
        f'<p>Dein Anmeldecode für <b>{app_name}</b>:</p>'
        f'<p style="font-size:32px;letter-spacing:6px;font-weight:700;margin:16px 0">{code}</p>'
        f'<p style="color:#666">Er ist 10 Minuten gültig.</p>{link_html}'
        f'<p style="color:#999;font-size:12px">Du hast keinen Code angefordert? Dann ignoriere diese E-Mail.</p>'
        f'</div>', subtype="html")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 587)
    user, pw = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if user:
                server.login(user, pw)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise AuthError(f"E-Mail konnte nicht gesendet werden ({e.__class__.__name__}). "
                        "Bitte SMTP-Einstellungen in .env prüfen.") from e
    return True


# ---------------------------------------------------------------------------
# Sitzungen (bleiben über Neuladen erhalten)
# ---------------------------------------------------------------------------
def create_session(user_id: int, path=None, ttl: int | None = None) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.connect(path) as con:
        con.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        con.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
                    (_hash(token), user_id, now + (ttl or session_ttl())))
    return token


def user_from_session(token: str, path=None) -> dict | None:
    if not token:
        return None
    with db.connect(path) as con:
        row = con.execute("SELECT user_id FROM sessions WHERE token_hash=? AND expires_at > ?",
                          (_hash(token), time.time())).fetchone()
    return db.get_user(row["user_id"], path) if row else None


def end_session(token: str, path=None) -> None:
    if token:
        with db.connect(path) as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))


def end_all_sessions(user_id: int, path=None) -> None:
    with db.connect(path) as con:
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
