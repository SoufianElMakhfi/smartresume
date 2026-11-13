# SmartResume – Projektregeln

## Nach jeder Änderung
Nach **jeder** kleinen Dateiänderung automatisch committen und pushen:
```
git add -A
git commit -m "..."
git push
```
Kein extra Nachfragen – einfach machen.

## Testen
Vor jedem Commit: `python -m pytest` (Unit-, Render- und UI-Tests mit Fake-KI). Änderungen an Prompts
zusätzlich live gegen ein echtes Modell prüfen (Keys in `.env`).

## Projekt
Mehrbenutzer-/Whitelabel-Streamlit-App: Bewerberprofil (CV-Upload oder manuell) + Stellenanzeige →
maßgeschneiderte Bewerbung als PDF (Typst). Details: `README.md`.

- `launcher.py` – Start: eigenes Fenster (pywebview/WebView2), Server als Unterprozess (`--server`) mit Start-Token
  (`SMARTRESUME_LOCAL_TOKEN`); auch für `SmartResume.exe`/Store-App (`build_exe.py`, `build_msix.py`)
- `app.py` – Login (Server: E-Mail-Code, erste E-Mail = Admin; lokal: nur E-Mail + Start-Token), Navigation
- `smartresume/` – Logik (`auth`, `bridge`, `config`, `paths`, `profile`, `db`, `llm`, `prompts`, `generate`, `quality`, `cv_import` (KI-Import, Zusammenführen), `cv_parse` (Import ohne KI, Standard), `scrape`, `render`, `branding`, `secret` (DPAPI für Keys/Passwörter), `backup` (ZIP-Sicherung))
- `smartresume/ui/` – Seiten (Bewerbung, Jobs, Profil, Meine Bewerbungen, Einstellungen inkl. Daten & Sicherung, KI einrichten, Hilfe & Info, Verwaltung – nur Server)
- Lokal (Fenster-App) keine Admin-/Server-Begriffe; `auth.local_mode()` / `auth.can_configure_ai()`
- `PRIVACY.md` – Datenschutzerklärung (bei neuen Datenflüssen anpassen!); `packaging/STORE_LISTING.md` – Store-Texte
- Pfade nur über `paths.py`: Programmdateien = `app_dir()`, Nutzerdaten (`.env`, `data/`) = `home_dir()` (bei der .exe neben der .exe)
- Lizenz: AGPL-3.0
- `template.typ` – liest alles aus `data.json` (kein String-Templating)
- KI: API-Modelle aus `.env` mit automatischem Wechsel; ohne Key/bei leerem Kontingent Abo-Modus (`bridge.py`: Kopieren & Einfügen über Gemini/ChatGPT, gleiche Prüfungen)
- **Keine persönlichen Daten ins Repo** (Open Source). Tests nutzen nur `tests/fixtures/` (erfundenes Profil)
- Speicherung: alles lokal in `data/smartresume.db` (SQLite, nicht im Git) – kein Cloud-Dienst
- `fonts/` – Lexend (statische Schnitte), Montserrat, Poppins – alle OFL, Lizenztexte liegen bei

## Grundprinzip Ehrlichkeit
Die KI liefert nur Texte und Referenzen (E1, S2 …). Firmen, Zeiträume, Ausbildung, Gehalt und Eintritt
kommen deterministisch aus dem Profil. Nicht übertreiben, nicht unterverkaufen – Regeln in `prompts.py`,
Prüfungen in `quality.py`.

## Design
- Schrift: Lexend, 10–10.5pt, weight 400
- Akzentfarbe: Standard Petrol `#0F5F6E` (pro Nutzer/Branding änderbar)
- Struktur: Seite 1 Deckblatt → Seite 2 Anschreiben → Seite 3 Lebenslauf
- Skills: 2-Spalten-Grid
- 2 Bullets pro Jobstation (optional 3)
