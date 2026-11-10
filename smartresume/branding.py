"""Whitelabel-Konfiguration.

Standardwerte können über branding.json im Projektordner (oder den Pfad in
SMARTRESUME_BRANDING) überschrieben werden – so lässt sich die App ohne
Codeänderung unter eigenem Namen, Logo und Farbe betreiben.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import paths


DEFAULT_BRANDING = {
    "app_name": "SmartResume",
    "tagline": "Maßgeschneiderte Bewerbungen in Minuten – ehrlich und überzeugend.",
    "page_icon": "📄",
    "logo": "",                    # Pfad zu PNG/SVG relativ zum Projektordner
    "accent_color": "#0F5F6E",     # Standard-Akzentfarbe der PDFs (Nutzer kann überschreiben)
    "pdf_font": "Lexend",          # muss in fonts/ liegen
    "allow_registration": True,    # Selbstregistrierung erlauben
    "invite_code": "",             # wenn gesetzt: Registrierung nur mit diesem Code
    "default_model": "",           # Label aus models.json, leer = erstes Modell
    "daily_limit_per_user": 0,     # max. KI-Bewerbungen/Tag pro Nutzer (0 = unbegrenzt, danach Abo-Modus)
    "support_email": "",
    "footer": "",
    "accent_presets": {
        "Petrol": "#0F5F6E", "Navy": "#1F3A5F", "Anthrazit": "#333333",
        "Bordeaux": "#7A1F2B", "Waldgrün": "#2E5E3E", "Aubergine": "#4B2E5A",
    },
}

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def load_branding() -> dict:
    b = json.loads(json.dumps(DEFAULT_BRANDING))
    path = Path(os.environ.get("SMARTRESUME_BRANDING", paths.home_dir() / "branding.json"))
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                b.update({k: v for k, v in override.items() if k in DEFAULT_BRANDING})
        except json.JSONDecodeError:
            pass
    if not _HEX.match(str(b["accent_color"])):
        b["accent_color"] = DEFAULT_BRANDING["accent_color"]
    if os.environ.get("SMARTRESUME_INVITE_CODE"):
        b["invite_code"] = os.environ["SMARTRESUME_INVITE_CODE"]
    return b
