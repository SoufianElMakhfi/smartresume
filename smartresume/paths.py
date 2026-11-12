"""Wo liegt was – im Quellcode-Ordner genauso wie in der fertigen SmartResume.exe.

- app_dir():  Programmdateien (app.py, template.typ, fonts/, icons/). In der .exe der
              entpackte Bundle-Ordner (schreibgeschützt behandeln).
- home_dir(): Dateien des Nutzers (.env mit KI-Keys, branding.json, models.json, data/).
              In der .exe der Ordner, in dem SmartResume.exe liegt – so bleibt alles
              lokal neben dem Programm und überlebt Neustarts.
              Als Store-App (MSIX) ist der Programmordner schreibgeschützt – dann
              %LOCALAPPDATA%/SmartResume (Windows leitet das in den App-Ordner um).
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


def packaged() -> bool:
    """Läuft als installierte Store-App (MSIX-Paket)?"""
    if sys.platform != "win32":
        return False
    import ctypes
    length = ctypes.c_uint32(0)
    try:   # 15700 = APPMODEL_ERROR_NO_PACKAGE, sonst 122 = Puffer zu klein → hat ein Paket
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != 15700
    except (AttributeError, OSError):
        return False


def package_family_name() -> str:
    """z. B. „Soubasa.smartresume_abc123xyz“ – leer, wenn nicht als Store-App gestartet."""
    if not packaged():
        return ""
    import ctypes
    length = ctypes.c_uint32(0)
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), None)
    buf = ctypes.create_unicode_buffer(length.value)
    if kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), buf) != 0:
        return ""
    return buf.value


def real_home_dir() -> Path:
    """Wo die Daten für den Explorer wirklich liegen. Als Store-App leitet Windows Schreibzugriffe auf
    %LOCALAPPDATA% in den Paketordner um – der Explorer sieht nur diesen echten Pfad."""
    home = home_dir()
    family = package_family_name()
    local = os.environ.get("LOCALAPPDATA")
    if family and local and not os.environ.get("SMARTRESUME_HOME"):
        return Path(local) / "Packages" / family / "LocalCache" / "Local" / "SmartResume"
    return home


def home_dir() -> Path:
    if os.environ.get("SMARTRESUME_HOME"):
        return Path(os.environ["SMARTRESUME_HOME"])
    if packaged():
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SmartResume"
    return Path(sys.executable).resolve().parent if frozen() else _SOURCE_ROOT


def data_dir() -> Path:
    return home_dir() / "data"


def env_file() -> Path:
    return home_dir() / ".env"
