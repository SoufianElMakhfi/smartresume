"""SQLite-Persistenz: Nutzer, Profile (inkl. Foto/Unterschrift/CV-Rohtext) und Bewerbungen.

Alles liegt lokal in EINER Datei auf der Festplatte – Standard: data/smartresume.db neben dem
Programm (nicht im Git, Pfad änderbar über SMARTRESUME_DB). Kein Cloud-Dienst nötig; zum Sichern
genügt es, diese Datei zu kopieren.

Alle Abfragen sind nach user_id getrennt – ein Nutzer sieht nie Daten eines anderen.
Login ohne Passwort: E-Mail + Einmal-Code (siehe auth.py).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from . import paths, secret
from .profile import empty_profile, normalize_profile


STATUS_OPTIONS = ["Erstellt", "Beworben", "Interview", "Angebot", "Absage", "Zurückgezogen"]


def db_path() -> Path:
    return Path(os.environ.get("SMARTRESUME_DB", paths.data_dir() / "smartresume.db"))


@contextmanager
def connect(path: Path | None = None):
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL COLLATE NOCASE,
    is_admin      INTEGER DEFAULT 0,
    created_at    TEXT,
    settings      TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    data         TEXT NOT NULL,
    photo        BLOB,
    signature    BLOB,
    cv_text      TEXT,
    cv_filename  TEXT,
    updated_at   TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company         TEXT,
    job_title       TEXT,
    employment_type TEXT,
    applied_at      TEXT,
    status          TEXT DEFAULT 'Beworben',
    job_text        TEXT,
    job_url         TEXT,
    pdf_bytes       BLOB,
    structured_data TEXT,
    notes           TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_app_user ON applications(user_id);
CREATE TABLE IF NOT EXISTS usage_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ts       TEXT NOT NULL,
    kind     TEXT NOT NULL,
    model    TEXT,
    tokens   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_log(user_id, ts);
CREATE TABLE IF NOT EXISTS login_codes (
    email      TEXT PRIMARY KEY COLLATE NOCASE,
    code_hash  TEXT NOT NULL,
    expires_at REAL NOT NULL,
    sent_at    REAL NOT NULL,
    attempts   INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
"""


def init_db(path: Path | None = None) -> None:
    with connect(path) as con:
        con.executescript(SCHEMA)
        if secret.available():                                    # alte Klartext-Mail-Passwörter verschlüsseln
            for row in con.execute("SELECT id, settings FROM users WHERE settings LIKE '%\"password\"%'").fetchall():
                s = _load_settings(row["settings"])
                mail = s.get("mail")
                if isinstance(mail, dict) and mail.get("password") and not mail["password"].startswith(secret.PREFIX):
                    mail["password"] = secret.protect(mail["password"])
                    con.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(s), row["id"]))


def _now() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


# ---------------------------------------------------------------------------
# Nutzer (Login per E-Mail-Code, keine Passwörter)
# ---------------------------------------------------------------------------
class UserError(ValueError):
    pass


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def normalize_email(email: str) -> str:
    """Kleinbuchstaben, ohne Leerzeichen. Wirft UserError bei ungültiger Adresse."""
    email = (email or "").strip().lower()
    if not _EMAIL.match(email):
        raise UserError("Bitte eine gültige E-Mail-Adresse eingeben.")
    return email


def _user_dict(row) -> dict:
    return {"id": row["id"], "email": row["email"], "is_admin": bool(row["is_admin"])}


def count_users(path=None) -> int:
    with connect(path) as con:
        return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def needs_setup(path=None) -> bool:
    """True, solange es noch keinen Admin gibt (Neuinstallation). Das erste Konto wird Admin."""
    with connect(path) as con:
        return con.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0] == 0


def create_user(email: str, is_admin: bool = False, path=None) -> int:
    email = normalize_email(email)
    try:
        with connect(path) as con:
            cur = con.execute(
                "INSERT INTO users (email, is_admin, created_at) VALUES (?,?,?)",
                (email, int(is_admin), _now()))
            uid = cur.lastrowid
            con.execute("INSERT INTO profiles (user_id, data, updated_at) VALUES (?,?,?)",
                        (uid, json.dumps(empty_profile(), ensure_ascii=False), _now()))
            return uid
    except sqlite3.IntegrityError:
        raise UserError("Für diese E-Mail gibt es bereits ein Konto.")


def get_user(user_id: int, path=None) -> dict | None:
    with connect(path) as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_dict(row) if row else None


def get_user_by_email(email: str, path=None) -> dict | None:
    try:
        email = normalize_email(email)
    except UserError:
        return None
    with connect(path) as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    return _user_dict(row) if row else None


def set_email(user_id: int, email: str, path=None) -> None:
    email = normalize_email(email)
    try:
        with connect(path) as con:
            con.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))
    except sqlite3.IntegrityError:
        raise UserError("Diese E-Mail gehört bereits zu einem anderen Konto.")


def list_users(path=None) -> list[dict]:
    with connect(path) as con:
        rows = con.execute(
            "SELECT u.id, u.email, u.is_admin, u.created_at, "
            "(SELECT COUNT(*) FROM applications a WHERE a.user_id=u.id) AS apps "
            "FROM users u ORDER BY u.id").fetchall()
    return [dict(r) for r in rows]


def delete_user(user_id: int, path=None) -> None:
    with connect(path) as con:
        con.execute("DELETE FROM users WHERE id=?", (user_id,))


def _load_settings(raw: str | None) -> dict:
    try:
        s = json.loads(raw or "{}")
        return s if isinstance(s, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_user_settings(user_id: int, path=None) -> dict:
    with connect(path) as con:
        row = con.execute("SELECT settings FROM users WHERE id=?", (user_id,)).fetchone()
    settings = _load_settings(row["settings"] if row else None)
    mail = settings.get("mail")
    if isinstance(mail, dict) and mail.get("password"):        # liegt verschlüsselt in der DB (secret.py)
        settings["mail"] = {**mail, "password": secret.reveal(mail["password"])}
    return settings


def save_user_settings(user_id: int, settings: dict, path=None) -> None:
    mail = settings.get("mail")
    if isinstance(mail, dict) and mail.get("password"):
        settings = {**settings, "mail": {**mail, "password": secret.protect(mail["password"])}}
    with connect(path) as con:
        con.execute("UPDATE users SET settings=? WHERE id=?", (json.dumps(settings), user_id))


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
def get_profile(user_id: int, path=None) -> dict:
    """Gibt {'data', 'photo', 'signature', 'cv_text', 'cv_filename'} zurück."""
    with connect(path) as con:
        row = con.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {"data": empty_profile(), "photo": None, "signature": None, "cv_text": "", "cv_filename": ""}
    return {
        "data": normalize_profile(json.loads(row["data"])),
        "photo": row["photo"], "signature": row["signature"],
        "cv_text": row["cv_text"] or "", "cv_filename": row["cv_filename"] or "",
    }


_UNSET = object()


def save_profile(user_id: int, data=_UNSET, photo=_UNSET, signature=_UNSET,
                 cv_text=_UNSET, cv_filename=_UNSET, path=None) -> None:
    """Aktualisiert nur die übergebenen Felder (None löscht Foto/Unterschrift)."""
    fields = {}
    if data is not _UNSET:
        fields["data"] = json.dumps(normalize_profile(data), ensure_ascii=False)
    for name, val in (("photo", photo), ("signature", signature),
                      ("cv_text", cv_text), ("cv_filename", cv_filename)):
        if val is not _UNSET:
            fields[name] = val
    if not fields:
        return
    fields["updated_at"] = _now()
    with connect(path) as con:
        exists = con.execute("SELECT 1 FROM profiles WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            con.execute("INSERT INTO profiles (user_id, data) VALUES (?,?)",
                        (user_id, json.dumps(empty_profile())))
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE profiles SET {sets} WHERE user_id=?", (*fields.values(), user_id))


# ---------------------------------------------------------------------------
# Bewerbungen
# ---------------------------------------------------------------------------
def save_application(user_id: int, company: str, job_title: str, employment_type: str,
                     job_text: str, job_url: str, pdf_bytes: bytes, structured: dict,
                     path=None, status: str = "Beworben") -> int:
    """status „Erstellt“: Unterlagen fertig, aber noch nicht verschickt (wird automatisch gespeichert)."""
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO applications (user_id, company, job_title, employment_type, applied_at, "
            "job_text, job_url, pdf_bytes, structured_data, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, company, job_title, employment_type, _now(), job_text, job_url, pdf_bytes,
             json.dumps(structured, ensure_ascii=False), status))
        return cur.lastrowid


def mark_applied(user_id: int, app_id: int, path=None) -> None:
    """Status „Beworben“ + Datum = jetzt (Unterlagen bleiben unverändert)."""
    update_application(user_id, app_id, path=path, status="Beworben", applied_at=_now())


def list_applications(user_id: int, path=None) -> list[dict]:
    with connect(path) as con:
        rows = con.execute(
            "SELECT id, company, job_title, employment_type, applied_at, status, notes, job_url "
            "FROM applications WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_application(user_id: int, app_id: int, path=None) -> dict | None:
    with connect(path) as con:
        row = con.execute("SELECT * FROM applications WHERE id=? AND user_id=?",
                          (app_id, user_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["structured"] = json.loads(d.pop("structured_data") or "null")
    except json.JSONDecodeError:
        d["structured"] = None
    return d


def update_application(user_id: int, app_id: int, path=None, **fields) -> None:
    allowed = {"status", "notes", "pdf_bytes", "structured_data", "company", "job_title", "applied_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with connect(path) as con:
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE applications SET {sets} WHERE id=? AND user_id=?",
                    (*fields.values(), app_id, user_id))


def delete_application(user_id: int, app_id: int, path=None) -> None:
    with connect(path) as con:
        con.execute("DELETE FROM applications WHERE id=? AND user_id=?", (app_id, user_id))


# ---------------------------------------------------------------------------
# Nutzungsprotokoll (Tokens pro Nutzer, Tageslimit für KI-Bewerbungen)
# ---------------------------------------------------------------------------
def log_usage(user_id: int, kind: str, model: str, tokens: int, path=None) -> None:
    with connect(path) as con:
        con.execute("INSERT INTO usage_log (user_id, ts, kind, model, tokens) VALUES (?,?,?,?,?)",
                    (user_id, datetime.now().isoformat(timespec="seconds"), kind, model, int(tokens or 0)))


def generations_today(user_id: int, path=None) -> int:
    """Anzahl KI-Bewerbungen heute (Abo-Modus zählt nicht – kostet nichts)."""
    today = datetime.now().strftime("%Y-%m-%d")
    with connect(path) as con:
        return con.execute("SELECT COUNT(*) FROM usage_log WHERE user_id=? AND kind='generate' AND ts >= ?",
                           (user_id, today)).fetchone()[0]


def usage_summary(path=None) -> list[dict]:
    with connect(path) as con:
        rows = con.execute(
            "SELECT u.email, COUNT(l.id) AS calls, COALESCE(SUM(l.tokens),0) AS tokens, "
            "MAX(l.ts) AS last_use FROM users u LEFT JOIN usage_log l ON l.user_id=u.id "
            "GROUP BY u.id ORDER BY tokens DESC").fetchall()
    return [dict(r) for r in rows]


def user_token_total(user_id: int, path=None) -> int:
    with connect(path) as con:
        return con.execute("SELECT COALESCE(SUM(tokens),0) FROM usage_log WHERE user_id=?",
                           (user_id,)).fetchone()[0]
