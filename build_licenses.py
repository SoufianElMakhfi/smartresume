"""Erzeugt THIRD_PARTY_LICENSES.txt – Lizenzen aller Bibliotheken, die in SmartResume.exe/der Store-App stecken.

Wird von build_exe.py und build_msix.py vor dem Bauen aufgerufen (Ausgabe: build/THIRD_PARTY_LICENSES.txt,
im Programm unter „Hilfe & Info“ lesbar). Geht von requirements.txt aus und folgt allen Abhängigkeiten der
installierten Pakete. Apache-2.0-Pakete verlangen, dass ihre NOTICE-Dateien mitgeliefert werden – die stehen
deshalb mit drin.

    python build_licenses.py            # schreibt build/THIRD_PARTY_LICENSES.txt
"""
from __future__ import annotations

import platform
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "build" / "THIRD_PARTY_LICENSES.txt"
EXTRA = ["pyinstaller"]   # Bootloader steckt in der .exe (GPL mit Ausnahme für gebündelte Programme)
_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.IGNORECASE)
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements() -> list[str]:
    names = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ";" in line and "win32" in line and sys.platform != "win32":
            continue
        m = _NAME.match(line)
        if m:
            names.append(m.group(1))
    return names + EXTRA


def _deps(dist: metadata.Distribution) -> list[str]:
    out = []
    for req in dist.requires or []:
        if "extra ==" in req:          # optionale Extras werden nicht mitgeliefert
            continue
        if ";" in req:
            marker = req.split(";", 1)[1]
            if "sys_platform" in marker and ("win32" in marker) != (sys.platform == "win32") and "!=" not in marker:
                continue
            if "python_version" in marker and "<" in marker and sys.version_info >= (3, 11):
                continue
        m = _NAME.match(req)
        if m:
            out.append(m.group(1))
    return out


def collect() -> list[metadata.Distribution]:
    seen: dict[str, metadata.Distribution] = {}
    todo = _requirements()
    while todo:
        name = todo.pop()
        key = _norm(name)
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[key] = dist
        todo += _deps(dist)
    return sorted(seen.values(), key=lambda d: _norm(d.metadata["Name"]))


def _license(dist: metadata.Distribution) -> str:
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 80 and "\n" not in lic:
        return lic
    classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    return ", ".join(classifiers) or (lic.splitlines()[0][:80] if lic else "siehe Lizenztext")


def _texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in dist.files or []:
        if _FILE.search(str(f).replace("\\", "/")):
            try:
                out.append((Path(str(f)).name, Path(f.locate()).read_text(encoding="utf-8", errors="replace").strip()))
            except (OSError, ValueError):
                pass
    if not out:
        lic = (dist.metadata.get("License") or "").strip()
        if "\n" in lic:
            out.append(("License", lic))
    return out


def render() -> str:
    dists = collect()
    lines = ["Lizenzen der in SmartResume enthaltenen Software", "=" * 48, "",
             "SmartResume selbst steht unter der GNU Affero General Public License v3.0 (siehe LICENSE).",
             f"Enthalten ist außerdem Python {platform.python_version()} (Python Software Foundation License).",
             "Schriften: Lexend, Montserrat, Poppins – SIL Open Font License 1.1 (Lizenztexte im Ordner fonts/).",
             "", "Übersicht", "-" * 9]
    for d in dists:
        lines.append(f"{d.metadata['Name']} {d.version} – {_license(d)}")
    for d in dists:
        texts = _texts(d)
        if not texts:
            continue
        lines += ["", "", "#" * 78, f"# {d.metadata['Name']} {d.version} ({_license(d)})", "#" * 78]
        for fname, text in texts:
            lines += ["", f"--- {fname} ---", text]
    return "\n".join(lines) + "\n"


def write(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write()
    print(f"{p} ({p.stat().st_size // 1024} KB)")
