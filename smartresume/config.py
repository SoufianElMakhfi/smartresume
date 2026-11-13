"""Lokale Konfiguration in .env (neben dem Programm): KI-Keys, SMTP usw.

Die Einrichtungsseite der App schreibt die Keys hierher – niemand muss eine Datei von Hand
bearbeiten. Bereits gesetzte Umgebungsvariablen (z. B. beim Hosting) haben Vorrang.
"""
from __future__ import annotations

import os
import re

from . import paths, secret

# Kostenlose Anbieter zuerst – das sind die, die die Einrichtungsseite prominent zeigt.
PROVIDERS = [
    {"env": "GEMINI_API_KEY", "name": "Google Gemini", "free": True,
     "url": "https://aistudio.google.com/apikey",
     "how": "Mit einem Google-Konto anmelden → „Create API key“ → Key kopieren."},
    {"env": "GROQ_API_KEY", "name": "Groq", "free": True,
     "url": "https://console.groq.com/keys",
     "how": "Konto anlegen → „Create API Key“ → Key kopieren."},
    # Kostenpflichtig – Claude zuerst
    {"env": "ANTHROPIC_API_KEY", "name": "Anthropic Claude", "free": False,
     "url": "https://console.anthropic.com/settings/keys",
     "how": "Beste Textqualität. Abrechnung nach Verbrauch: In der Anthropic Console Guthaben aufladen → "
            "„Create Key“ → Key kopieren. Danach wählst du hier, welches Claude-Modell schreibt."},
    {"env": "OPENROUTER_API_KEY", "name": "OpenRouter", "free": False,
     "url": "https://openrouter.ai/keys", "how": "Guthaben-basiert, sehr günstig."},
    {"env": "MISTRAL_API_KEY", "name": "Mistral", "free": False,
     "url": "https://console.mistral.ai/api-keys",
     "how": "Europäischer Anbieter. API nur mit Prepaid-Guthaben (ab 10 €) – kein Gratis-Plan mehr."},
]

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_from_file: set[str] = set()   # Variablen, die aus .env stammen (dürfen überschrieben werden)


def load_env() -> None:
    """Umgebungsvariablen > .env.local > .env (ohne Zusatzabhängigkeit).
    Keys/Passwörter stehen verschlüsselt in .env (secret.py); alte Klartext-Einträge werden dabei verschlüsselt."""
    for name in (".env.local", ".env"):
        p = paths.home_dir() / name
        if not p.exists():
            continue
        plain: dict[str, str] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if v and secret.is_secret_name(k) and not v.startswith(secret.PREFIX):
                    plain[k] = v
                v = secret.reveal(v)
                if k not in os.environ:
                    os.environ[k] = v
                    _from_file.add(k)
        if plain and name == ".env" and secret.available():
            try:
                _write_env(p, plain)
            except OSError:
                pass


def is_set(env: str) -> bool:
    return bool(os.environ.get(env, "").strip())


def set_externally(env: str) -> bool:
    """True, wenn der Wert vom System/Hoster kommt und nicht aus .env (dann nicht in der App änderbar)."""
    return is_set(env) and env not in _from_file


def _write_env(path, values: dict[str, str]) -> None:
    """Setzt Einträge in einer .env-Datei (Keys/Passwörter verschlüsselt); andere Zeilen bleiben erhalten."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    todo = {k: (v or "").strip() for k, v in values.items()}
    todo = {k: secret.protect(v) if secret.is_secret_name(k) else v for k, v in todo.items()}
    out = []
    for line in lines:
        m = _LINE.match(line)
        if m and m.group(1) in todo:
            val = todo.pop(m.group(1))
            if val:
                out.append(f"{m.group(1)}={val}")
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in todo.items() if v]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).strip() + "\n", encoding="utf-8")


def save_values(values: dict[str, str]) -> None:
    """Schreibt Werte in .env (vorhandene Zeilen und Kommentare bleiben erhalten) und
    übernimmt sie sofort in die laufende App. Leerer Wert = Eintrag entfernen."""
    _write_env(paths.env_file(), values)
    for k, v in values.items():
        v = (v or "").strip()
        if v:
            os.environ[k] = v
            _from_file.add(k)
        elif k in _from_file:
            os.environ.pop(k, None)
            _from_file.discard(k)
