"""Wo liegt was – im Quellcode-Ordner genauso wie in der fertigen SmartResume.exe.

- app_dir():  Programmdateien (app.py, template.typ, fonts/, icons/). In der .exe der
              entpackte Bundle-Ordner (schreibgeschützt behandeln).
- home_dir(): Dateien des Nutzers (.env mit KI-Keys, branding.json, models.json, data/).
              In der .exe der Ordner, in dem SmartResume.exe liegt – so bleibt alles
              lokal neben dem Programm und überlebt Neustarts.
SMARTRESUME_HOME überschreibt home_dir() (z. B. für Tests oder portable Installationen).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", _SOURCE_ROOT))


def home_dir() -> Path:
    if os.environ.get("SMARTRESUME_HOME"):
        return Path(os.environ["SMARTRESUME_HOME"])
    return Path(sys.executable).resolve().parent if frozen() else _SOURCE_ROOT


def data_dir() -> Path:
    return home_dir() / "data"


def env_file() -> Path:
    return home_dir() / ".env"
