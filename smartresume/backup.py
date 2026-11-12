"""Komplette Sicherung eines Kontos als ZIP – und Wiederherstellung.

Wichtig für die Store-App: Windows löscht beim Deinstallieren alle Daten der App. Mit dieser Datei kommt
alles zurück (auch auf einem neuen PC): Profil, Foto, Unterschrift, gespeicherter Lebenslauf-Text,
Einstellungen und alle Bewerbungen samt PDF. Die PDFs liegen zusätzlich lesbar im Ordner „Bewerbungen/“.

Nicht enthalten: das Mail-Passwort (ist an diesen PC gebunden, siehe secret.py) und KI-Keys.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime

from . import __version__, db

FORMAT = "smartresume-backup"
VERSION = 1
MAX_BYTES = 200 * 1024 * 1024
_APP_FIELDS = ("company", "job_title", "employment_type", "applied_at", "status", "job_text", "job_url",
               "notes", "structured_data")


class BackupError(ValueError):
    pass


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-. äöüÄÖÜß]+", "_", name or "").strip(" ._")[:60] or "Bewerbung"


def filename() -> str:
    return f"SmartResume-Sicherung-{datetime.now():%Y-%m-%d}.zip"


def export_user(user_id: int, path=None) -> bytes:
    prof = db.get_profile(user_id, path)
    settings = db.get_user_settings(user_id, path)
    if isinstance(settings.get("mail"), dict):
        settings["mail"] = {k: v for k, v in settings["mail"].items() if k != "password"}
    with db.connect(path) as con:
        rows = [dict(r) for r in con.execute(
            f"SELECT id, {', '.join(_APP_FIELDS)}, pdf_bytes FROM applications WHERE user_id=? ORDER BY id",
            (user_id,)).fetchall()]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("smartresume.json", json.dumps({"format": FORMAT, "version": VERSION, "app_version": __version__,
                                                   "created": datetime.now().isoformat(timespec="seconds")}))
        z.writestr("profil.json", json.dumps({"data": prof["data"], "cv_text": prof["cv_text"] or "",
                                              "cv_filename": prof["cv_filename"] or ""},
                                             ensure_ascii=False, indent=2))
        z.writestr("einstellungen.json", json.dumps(settings, ensure_ascii=False, indent=2))
        if prof["photo"]:
            z.writestr("foto.jpg", prof["photo"])
        if prof["signature"]:
            z.writestr("unterschrift.png", prof["signature"])
        apps = []
        for r in rows:
            pdf = r.pop("pdf_bytes")
            entry = {k: r[k] for k in _APP_FIELDS}
            if pdf:
                entry["pdf"] = f"Bewerbungen/{r['id']:04d} {_safe(r['company'])} - {_safe(r['job_title'])}.pdf"
                z.writestr(entry["pdf"], pdf)
            apps.append(entry)
        z.writestr("bewerbungen.json", json.dumps(apps, ensure_ascii=False, indent=2))
    return buf.getvalue()


def read_backup(data: bytes) -> dict:
    """Prüft die Datei und gibt eine Übersicht zurück (für die Rückfrage vor dem Wiederherstellen)."""
    if len(data) > MAX_BYTES:
        raise BackupError("Die Datei ist zu groß.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        meta = json.loads(z.read("smartresume.json"))
        apps = json.loads(z.read("bewerbungen.json"))
        prof = json.loads(z.read("profil.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise BackupError("Das ist keine SmartResume-Sicherung (ZIP-Datei aus „Daten sichern“).") from None
    if meta.get("format") != FORMAT:
        raise BackupError("Das ist keine SmartResume-Sicherung.")
    if int(meta.get("version", 0)) > VERSION:
        raise BackupError("Diese Sicherung stammt aus einer neueren SmartResume-Version – bitte zuerst aktualisieren.")
    name = ((prof.get("data") or {}).get("personal") or {}).get("name", "")
    return {"created": meta.get("created", ""), "applications": len(apps), "name": name}


def import_user(user_id: int, data: bytes, path=None) -> dict:
    """Ersetzt Profil, Einstellungen und Bewerbungen dieses Kontos durch die Sicherung."""
    info = read_backup(data)
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    prof = json.loads(z.read("profil.json"))
    apps = json.loads(z.read("bewerbungen.json"))
    settings = json.loads(z.read("einstellungen.json")) if "einstellungen.json" in names else {}

    current = db.get_user_settings(user_id, path)
    if isinstance(settings.get("mail"), dict) and isinstance(current.get("mail"), dict) \
            and current["mail"].get("password") and current["mail"].get("address") == settings["mail"].get("address"):
        settings["mail"]["password"] = current["mail"]["password"]   # Passwort dieses PCs behalten
    db.save_user_settings(user_id, settings if isinstance(settings, dict) else {}, path)
    db.save_profile(user_id, data=prof.get("data") or {},
                    photo=z.read("foto.jpg") if "foto.jpg" in names else None,
                    signature=z.read("unterschrift.png") if "unterschrift.png" in names else None,
                    cv_text=prof.get("cv_text", ""), cv_filename=prof.get("cv_filename", ""), path=path)
    with db.connect(path) as con:
        con.execute("DELETE FROM applications WHERE user_id=?", (user_id,))
        for a in apps:
            pdf = z.read(a["pdf"]) if a.get("pdf") in names else None
            sd = a.get("structured_data")
            con.execute(
                f"INSERT INTO applications (user_id, {', '.join(_APP_FIELDS)}, pdf_bytes) "
                f"VALUES (?{', ?' * len(_APP_FIELDS)}, ?)",
                (user_id, *[a.get(k) if k != "structured_data" else
                            (sd if isinstance(sd, str) or sd is None else json.dumps(sd, ensure_ascii=False))
                            for k in _APP_FIELDS], pdf))
    return info
