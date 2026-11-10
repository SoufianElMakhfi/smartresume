"""Startprogramm für SmartResume.exe (und `python launcher.py`).

Startet den Streamlit-Server auf einem freien Port, öffnet den Browser, sobald die App bereit ist,
und läuft, bis das Fenster geschlossen wird. Alle Daten (data/, .env) liegen neben der .exe.
Umgebungsvariablen für Tests/Server: SMARTRESUME_PORT, SMARTRESUME_NO_BROWSER=1.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def _free_port(start: int = 8501) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _open_when_ready(url: str) -> None:
    for _ in range(240):
        try:
            with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as r:
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(0.5)


def selftest() -> int:
    """Prüft, ob alles Nötige an Bord ist (für Build-Kontrolle): Module, PDF-Erzeugung, Startseite.
    Hinterlässt keine Dateien."""
    import importlib
    import tempfile

    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SMARTRESUME_HOME"] = tmp
        for mod in ("smartresume.ui.generate_page", "smartresume.ui.profile_page", "smartresume.ui.setup_page",
                    "smartresume.ui.settings_page", "smartresume.ui.tracking_page", "smartresume.ui.admin_page",
                    "google.genai", "anthropic", "pypdf", "docx", "bs4", "PIL", "pandas", "requests"):
            importlib.import_module(mod)
        print("Module: ok")

        from smartresume import generate, render
        from smartresume.profile import normalize_profile
        profile = normalize_profile({
            "personal": {"name": "Max Mustermann", "email": "max@example.com", "zip_city": "50667 Köln"},
            "experience": [{"company": "Beispiel GmbH", "role": "Entwickler", "start": "01/2022", "end": "Heute",
                            "location": "Köln", "bullets": ["Webanwendungen entwickelt", "Kunden beraten"]}],
            "education": [{"institution": "Beispiel Akademie", "degree": "Weiterbildung", "start": "2020",
                           "end": "2021", "location": "Online"}],
            "skills": [{"category": "Frontend", "items": ["React", "TypeScript"]}],
        })
        ai = {"job": {"company": "Test AG", "job_title": "Entwickler"}, "summary": "Ich entwickle Webanwendungen.",
              "experience": [{"ref": "E1", "bullets": ["Webanwendungen entwickelt"]}],
              "skills": [{"ref": "S1", "items": ["React"]}],
              "cover_letter": {"p1": "Eins.", "p2": "Zwei.", "p3": "Drei.", "p4": "Vier."}}
        pdf = render.render_pdf(generate.assemble(ai, profile, "Vollzeit"), profile)
        assert pdf[:4] == b"%PDF" and render.count_pages(pdf) >= 3, "PDF unvollständig"
        print(f"PDF: ok ({render.count_pages(pdf)} Seiten)")

        from smartresume import paths
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(paths.app_dir() / "app.py"), default_timeout=60)
        at.run()
        assert not at.exception, at.exception
        assert any("Ersteinrichtung" in s.value for s in at.subheader), "Startseite unvollständig"
        print("Startseite: ok")
    print("SELFTEST OK")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    from smartresume import paths

    port = int(os.environ.get("SMARTRESUME_PORT") or _free_port())
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print(" SmartResume läuft.")
    print(f" Im Browser: {url}")
    print(f" Deine Daten: {paths.data_dir()}")
    print(" Dieses Fenster offen lassen – Schließen beendet SmartResume.")
    print("=" * 60, flush=True)
    if not os.environ.get("SMARTRESUME_NO_BROWSER"):
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit", "run", str(paths.app_dir() / "app.py"),
        "--server.port", str(port),
        "--server.address", "127.0.0.1",   # nur dieser PC, keine Firewall-Abfrage
        "--server.headless", "true",
        "--server.maxUploadSize", "10",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
        "--logger.level", "error",          # Konsole ruhig halten
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
