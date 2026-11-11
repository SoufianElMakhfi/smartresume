"""Baut das Store-Paket dist/SmartResume-<version>.msix für den Microsoft Store.

    pip install -r requirements.txt pyinstaller
    python build_msix.py                 # Version aus smartresume/__init__.py (2.0.0 → 2.0.0.0)
    python build_msix.py --version 2.0.1

Das Paket ist unsigniert – der Store signiert es nach der Prüfung selbst. Hochladen in Partner Center
unter „Pakete“ einer Übermittlung. Jede neue Einreichung braucht eine höhere Version.
Braucht makeappx.exe (Windows SDK; auf GitHub-Windows-Runnern vorhanden, sonst MAKEAPPX=Pfad setzen).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

from build_exe import pyinstaller_args
from smartresume import __version__

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "packaging"
WORK = ROOT / "build" / "msix"


def store_version(version: str) -> str:
    """Store-Format a.b.c.0 (die vierte Stelle muss 0 sein)."""
    parts = re.findall(r"\d+", version)[:3]
    if not parts:
        raise SystemExit(f"Ungültige Version: {version!r}")
    return ".".join((parts + ["0", "0"])[:3] + ["0"])


def manifest(version: str) -> str:
    identity = json.loads((PKG / "store.json").read_text(encoding="utf-8"))
    text = (PKG / "msix" / "AppxManifest.template.xml").read_text(encoding="utf-8")
    values = {**{k: v for k, v in identity.items() if not k.startswith("_")}, "version": version}
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    if "{" in text.split("-->", 1)[1]:
        raise SystemExit("Platzhalter im Manifest nicht ersetzt – packaging/store.json prüfen.")
    return text


def makeappx() -> str:
    if os.environ.get("MAKEAPPX"):
        return os.environ["MAKEAPPX"]
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe"))
    if not found:
        raise SystemExit("makeappx.exe nicht gefunden – Windows SDK installieren oder MAKEAPPX=Pfad setzen.")
    return found[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=__version__)
    parser.add_argument("--skip-build", action="store_true", help="vorhandenen Programmordner wiederverwenden")
    args = parser.parse_args()
    version = store_version(args.version)

    app = WORK / "app"
    if not args.skip_build:
        PyInstaller.__main__.run(pyinstaller_args(onefile=False) + [
            "--distpath", str(app), "--workpath", str(WORK / "pyinstaller")])

    stage = WORK / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    # python-docx bringt seine Vorlage zusätzlich entpackt mit („[Content_Types].xml“, „_rels/“) – diese
    # Namen sind im MSIX-Format reserviert. Gebraucht wird nur default.docx, der Ordner bleibt draußen.
    shutil.copytree(app / "SmartResume", stage / "SmartResume",
                    ignore=shutil.ignore_patterns("default-docx-template"))
    shutil.copytree(PKG / "msix" / "Assets", stage / "Assets")
    (stage / "AppxManifest.xml").write_text(manifest(version), encoding="utf-8")

    out = ROOT / "dist" / f"SmartResume-{version}.msix"
    out.parent.mkdir(exist_ok=True)
    subprocess.run([makeappx(), "pack", "/d", str(stage), "/p", str(out), "/o"], check=True)
    print(f"\nFertig: {out}  ({out.stat().st_size / 1e6:.0f} MB, Version {version})")


if __name__ == "__main__":
    sys.exit(main())
