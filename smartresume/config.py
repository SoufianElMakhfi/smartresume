"""Lokale Konfiguration in .env (neben dem Programm): KI-Keys, SMTP usw.

Die Einrichtungsseite der App schreibt die Keys hierher – niemand muss eine Datei von Hand
bearbeiten. Bereits gesetzte Umgebungsvariablen (z. B. beim Hosting) haben Vorrang.
"""
from __future__ import annotations

import os
import re

from . import paths

# Kostenlose Anbieter zuerst – das sind die, die die Einrichtungsseite prominent zeigt.
PROVIDERS = [
    {"env": "GEMINI_API_KEY", "name": "Google Gemini", "free": True,
     "url": "https://aistudio.google.com/apikey",
     "how": "Mit einem Google-Konto anmelden → „Create API key“ → Key kopieren."},
    {"env": "MISTRAL_API_KEY", "name": "Mistral", "free": True,
     "url": "https://console.mistral.ai/api-keys",
     "plan_url": "https://admin.mistral.ai/plateforme/subscription",
     "how": "1. Gratis-Plan: anmelden → „Compare plans“ / „Upgrade“ → „Experiment“ wählen (kostenlos, keine "
            "Kreditkarte, Handynummer per SMS bestätigen). 2. Key holen: „Neuer Schlüssel“ → Key kopieren."},
    {"env": "GROQ_API_KEY", "name": "Groq", "free": True,
     "url": "https://console.groq.com/keys",
     "how": "Konto anlegen → „Create API Key“ → Key kopieren."},
    {"env": "OPENROUTER_API_KEY", "name": "OpenRouter", "free": False,
     "url": "https://openrouter.ai/keys", "how": "Guthaben-basiert, sehr günstig."},
    {"env": "ANTHROPIC_API_KEY", "name": "Anthropic Claude", "free": False,
     "url": "https://console.anthropic.com/settings/keys", "how": "Kostenpflichtig, sehr gute Textqualität."},
]

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_from_file: set[str] = set()   # Variablen, die aus .env stammen (dürfen überschrieben werden)


def load_env() -> None:
    """Umgebungsvariablen > .env.local > .env (ohne Zusatzabhängigkeit)."""
    for name in (".env.local", ".env"):
        p = paths.home_dir() / name
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
                    _from_file.add(k)


def is_set(env: str) -> bool:
    return bool(os.environ.get(env, "").strip())


def set_externally(env: str) -> bool:
    """True, wenn der Wert vom System/Hoster kommt und nicht aus .env (dann nicht in der App änderbar)."""
    return is_set(env) and env not in _from_file


def save_values(values: dict[str, str]) -> None:
    """Schreibt Werte in .env (vorhandene Zeilen und Kommentare bleiben erhalten) und
    übernimmt sie sofort in die laufende App. Leerer Wert = Eintrag entfernen."""
    path = paths.env_file()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    todo = {k: (v or "").strip() for k, v in values.items()}
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
    for k, v in values.items():
        v = (v or "").strip()
        if v:
            os.environ[k] = v
            _from_file.add(k)
        elif k in _from_file:
            os.environ.pop(k, None)
            _from_file.discard(k)
