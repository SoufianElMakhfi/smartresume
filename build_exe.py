"""Baut dist/SmartResume.exe – eine einzige Datei, ohne Python-Installation lauffähig.

    pip install -r requirements.txt pyinstaller
    python build_exe.py

Die .exe legt beim Start ihre Daten (data/, .env) im selben Ordner an, in dem sie liegt.
Für das Store-Paket baut build_msix.py mit pyinstaller_args(onefile=False) einen Programmordner.
"""
from __future__ import annotations

import os
import sys

import PyInstaller.__main__

SEP = os.pathsep  # ";" unter Windows, ":" sonst


def pyinstaller_args(onefile: bool = True) -> list[str]:
    return [
        "launcher.py",
        "--name", "SmartResume",
        "--onefile" if onefile else "--onedir",
        "--console",            # Fenster zeigt Adresse/Hinweise; Schließen beendet die App
        "--icon", os.path.join("packaging", "icon.ico"),
        "--noconfirm",
        "--clean",
        "--add-data", f"app.py{SEP}.",
        "--add-data", f"template.typ{SEP}.",
        "--add-data", f"fonts{SEP}fonts",
        "--add-data", f"icons{SEP}icons",
        "--add-data", f"LICENSE{SEP}.",
        "--collect-submodules", "smartresume",
        "--collect-all", "streamlit",
        "--collect-all", "typst",
        "--copy-metadata", "streamlit",
        "--copy-metadata", "google-genai",
        "--copy-metadata", "anthropic",
        "--hidden-import", "google.genai",
        "--hidden-import", "anthropic",
        "--hidden-import", "pypdf",
        "--hidden-import", "docx",
        "--hidden-import", "bs4",
        "--hidden-import", "PIL",
        "--hidden-import", "pandas",
    ]


def main() -> None:
    PyInstaller.__main__.run(pyinstaller_args() + sys.argv[1:])


if __name__ == "__main__":
    main()
