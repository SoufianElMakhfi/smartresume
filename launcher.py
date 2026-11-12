"""Startprogramm für SmartResume.exe, die Store-App und `python launcher.py`.

Normaler Start: ein eigenes App-Fenster (WebView2 über pywebview) – kein Browser, keine Konsole.
Der Streamlit-Server läuft als Unterprozess (`--server`) nur auf 127.0.0.1 und endet mit dem Fenster.
Gibt es kein WebView2, öffnet sich ersatzweise der Standardbrowser.

Jeder Start erzeugt ein geheimes Start-Token (SMARTRESUME_LOCAL_TOKEN). Nur das eigene Fenster kennt es –
andere Windows-Konten oder Webseiten, die 127.0.0.1 erreichen, kommen so nicht in die App.

Umgebungsvariablen für Tests/Server: SMARTRESUME_PORT, SMARTRESUME_NO_BROWSER=1 (Server im Vordergrund,
gibt die Adresse samt Token aus).
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

APP_TITLE = "SmartResume"
ACCENT = "#0F5F6E"

LOADING_HTML = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<style>
  html,body{{height:100%;margin:0}}
  body{{display:flex;align-items:center;justify-content:center;font-family:'Segoe UI',system-ui,sans-serif;
       background:#fff;color:#1f2933}}
  @media (prefers-color-scheme: dark){{body{{background:#1b1b1b;color:#e8e8e8}}}}
  .box{{text-align:center}} h1{{font-weight:600;font-size:28px;margin:18px 0 6px}} p{{opacity:.7;margin:0}}
  .spin{{width:38px;height:38px;border:4px solid {ACCENT}33;border-top-color:{ACCENT};border-radius:50%;
        margin:auto;animation:s 0.9s linear infinite}} @keyframes s{{to{{transform:rotate(360deg)}}}}
</style></head><body><div class="box"><div class="spin"></div><h1>{APP_TITLE}</h1>
<p id="msg">wird gestartet …</p></div></body></html>"""

ERROR_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8"><style>
body{font-family:'Segoe UI',system-ui,sans-serif;padding:40px;max-width:640px;margin:auto;color:#1f2933}
code{background:#f1f1f1;padding:2px 6px;border-radius:4px}</style></head><body>
<h2>SmartResume konnte nicht starten</h2>
<p>Bitte das Fenster schließen und SmartResume erneut öffnen. Tritt der Fehler wieder auf, schick bitte die
Protokolldatei an den Support:</p><p><code>%s</code></p></body></html>"""


def _free_port(start: int = 8501) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/_stcore/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _wait_ready(url: str, proc: subprocess.Popen | None = None, timeout: float = 120) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if _healthy(url):
            return True
        if proc is not None and proc.poll() is not None:   # Server ist abgestürzt
            return False
        time.sleep(0.25)
    return False


def _log_file():
    from smartresume import paths
    folder = paths.home_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "smartresume.log"


def _ensure_streams() -> None:
    """Ohne Konsole (Fenster-Programm) sind sys.stdout/stderr None – dann ins Protokoll schreiben."""
    if sys.stdout is None or sys.stderr is None:
        log = open(_log_file(), "a", encoding="utf-8", buffering=1)  # noqa: SIM115 – lebt so lange wie der Prozess
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log


def _watch_parent() -> None:
    """Server-Prozess: endet, sobald das Fenster-Programm weg ist (auch nach Absturz oder Task-Manager)."""
    pid = int(os.environ.get("SMARTRESUME_PARENT_PID") or 0)
    if not pid or sys.platform != "win32":
        return
    import ctypes
    SYNCHRONIZE, INFINITE = 0x00100000, 0xFFFFFFFF
    handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        os._exit(0)

    def wait() -> None:
        ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
        os._exit(0)
    threading.Thread(target=wait, daemon=True).start()


def server_args(port: int) -> list[str]:
    from smartresume import paths
    return [
        "streamlit", "run", str(paths.app_dir() / "app.py"),
        "--server.port", str(port),
        "--server.address", "127.0.0.1",   # nur dieser PC, keine Firewall-Abfrage
        "--server.headless", "true",
        "--server.maxUploadSize", "200",   # nur für Sicherungen; andere Felder: 10 MB
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
        "--client.toolbarMode", "viewer",   # kein „Deploy“-Knopf / Entwicklermenü
        "--theme.primaryColor", ACCENT,     # Petrol statt Streamlit-Rot
        "--logger.level", "error",
    ]


def run_server(port: int) -> int:
    """Streamlit im Vordergrund dieses Prozesses (braucht den Haupt-Thread)."""
    os.environ["SMARTRESUME_LOCAL"] = "1"   # nur über 127.0.0.1 erreichbar → Anmeldung nur mit E-Mail
    _ensure_streams()
    _watch_parent()
    from streamlit.web import cli as stcli
    sys.argv = server_args(port)
    return stcli.main()


def _server_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server"]
    return [sys.executable, os.path.abspath(__file__), "--server"]


def run_window() -> int:
    """Eigenes App-Fenster; der Server läuft als Unterprozess und endet mit dem Fenster."""
    from smartresume import paths

    port = int(os.environ.get("SMARTRESUME_PORT") or _free_port())
    token = secrets.token_urlsafe(24)
    url = f"http://127.0.0.1:{port}"
    log_path = _log_file()
    env = {**os.environ, "SMARTRESUME_PORT": str(port), "SMARTRESUME_LOCAL_TOKEN": token,
           "SMARTRESUME_PARENT_PID": str(os.getpid())}
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"SmartResume {time.strftime('%Y-%m-%d %H:%M:%S')} – Daten: {paths.data_dir()}\n")
        log.flush()
        proc = subprocess.Popen(_server_command(), env=env, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    app_url = f"{url}/?k={token}"
    try:
        try:
            import webview
        except Exception:  # noqa: BLE001 – kein pywebview/WebView2 → Browser
            webview = None
        if webview is None:
            return _run_in_browser(app_url, url, proc)

        webview.settings["ALLOW_DOWNLOADS"] = True              # PDFs/Sicherungen über „Speichern unter“
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # Gemini/ChatGPT, Hilfe-Links → Browser
        if os.environ.get("SMARTRESUME_DEBUG_PORT"):                 # nur für automatische Oberflächentests
            webview.settings["REMOTE_DEBUGGING_PORT"] = int(os.environ["SMARTRESUME_DEBUG_PORT"])
        window = webview.create_window(APP_TITLE, html=LOADING_HTML, width=1280, height=900,
                                       min_size=(420, 560), background_color="#FFFFFF", text_select=True)

        def load() -> None:
            if _wait_ready(url, proc):
                window.load_url(app_url)
            else:
                window.load_html(ERROR_HTML % log_path)

        storage = paths.home_dir() / "webview"     # Cookies → angemeldet bleiben
        storage.mkdir(parents=True, exist_ok=True)
        icon = paths.app_dir() / "packaging" / "icon.ico"
        try:
            webview.start(load, private_mode=False, storage_path=str(storage),
                          icon=str(icon) if icon.exists() else None)
        except Exception:  # noqa: BLE001 – WebView2 fehlt oder startet nicht → Browser
            return _run_in_browser(app_url, url, proc)
        return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _run_in_browser(app_url: str, url: str, proc: subprocess.Popen) -> int:
    if _wait_ready(url, proc):
        webbrowser.open(app_url)
    return proc.wait()


def run_headless() -> int:
    """SMARTRESUME_NO_BROWSER=1: Server im Vordergrund (Tests, Server ohne Bildschirm)."""
    from smartresume import paths
    port = int(os.environ.get("SMARTRESUME_PORT") or _free_port())
    token = os.environ.setdefault("SMARTRESUME_LOCAL_TOKEN", secrets.token_urlsafe(24))
    print("=" * 60)
    print(" SmartResume läuft.")
    print(f" Adresse: http://127.0.0.1:{port}/?k={token}")
    print(f" Deine Daten: {paths.data_dir()}")
    print("=" * 60, flush=True)
    return run_server(port)


def selftest() -> int:
    """Prüft, ob alles Nötige an Bord ist (für Build-Kontrolle): Module, PDF-Erzeugung, Startseite.
    Hinterlässt keine Dateien."""
    import importlib
    import tempfile

    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SMARTRESUME_HOME"] = tmp
        _ensure_streams()
        mods = ["smartresume.ui.generate_page", "smartresume.ui.profile_page", "smartresume.ui.setup_page",
                "smartresume.ui.settings_page", "smartresume.ui.jobs_page", "smartresume.ui.tracking_page",
                "smartresume.ui.admin_page",
                "google.genai", "anthropic", "pypdf", "docx", "bs4", "PIL", "pandas", "requests"]
        if sys.platform == "win32":
            mods += ["webview", "clr"]
        for mod in mods:
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

        from smartresume import paths, secret
        assert secret.reveal(secret.protect("test-123")) == "test-123", "Verschlüsselung defekt"
        print("Verschlüsselung: ok")

        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(paths.app_dir() / "app.py"), default_timeout=60)
        at.run()
        assert not at.exception, at.exception
        assert any("Willkommen" in s.value or "Ersteinrichtung" in s.value for s in at.subheader), \
            "Startseite unvollständig"
        print("Startseite: ok")
    print("SELFTEST OK")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if "--server" in sys.argv:
        return run_server(int(os.environ.get("SMARTRESUME_PORT") or _free_port()))
    if os.environ.get("SMARTRESUME_NO_BROWSER"):
        return run_headless()
    return run_window()


if __name__ == "__main__":
    sys.exit(main())
