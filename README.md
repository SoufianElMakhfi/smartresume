# SmartResume

Streamlit-App, die aus einem Bewerberprofil und einer Stellenanzeige maßgeschneiderte
Bewerbungsunterlagen erstellt: **Deckblatt → Anschreiben → Lebenslauf** als PDF (Typst).
Mehrbenutzerfähig, Login per E-Mail-Code, Whitelabel über `branding.json`.

**Funktioniert auch ganz ohne API-Key:** Dann entsteht der Text über das eigene Gemini- oder
ChatGPT-Konto des Nutzers (Kopieren & Einfügen, auch mit kostenlosen Konten) – mit denselben Regeln
und Prüfungen wie über die API.

## Schnellstart

**Windows – eine Datei, nichts installieren:**

1. `SmartResume.exe` aus den [Releases](../../releases) herunterladen, in einen eigenen Ordner legen
   (z. B. `Dokumente\SmartResume`) und doppelklicken. Der Browser öffnet sich automatisch.
2. Mit deiner E-Mail anmelden – lokal wird der Code direkt angezeigt.
3. Unter **„🔑 KI einrichten“** einen kostenlosen Gemini-Key (optional zusätzlich Groq) einfügen (Link und Anleitung
   stehen dabei), **Testen**, **Speichern** – fertig.

Alle Daten (`data/`, `.env` mit den Keys) liegen neben der `.exe` auf deiner Festplatte. Das schwarze Fenster
offen lassen; Schließen beendet SmartResume. Hinweis: Windows SmartScreen kann bei neuen, nicht signierten
Programmen warnen („Weitere Informationen“ → „Trotzdem ausführen“).

**Aus dem Quellcode (Windows, macOS, Linux):** Python 3.11+ installieren, dann unter Windows
`SmartResume starten.bat` doppelklicken – oder:

```bash
pip install -r requirements.txt
python launcher.py                   # oder: streamlit run app.py
```

Für die PDF-Erstellung reicht das Python-Paket `typst` (in `requirements.txt`); die Typst-CLI
(`winget install --id Typst.Typst`, `brew install typst`) wird genutzt, wenn vorhanden.

Die erste E-Mail-Adresse, die sich anmeldet, wird **Admin** und landet direkt bei „KI einrichten“.

## KI: API mit automatischem Rückfall auf Gemini/ChatGPT

1. **API-Modelle** mit kostenlosen Keys (Gemini, Groq) oder kostenpflichtigen (Mistral, OpenRouter, Claude) – eingetragen in der App unter
   **„🔑 KI einrichten“** (nur Admins; gespeichert lokal in `.env`). Ist ein Kontingent erschöpft oder ein
   Modell überlastet, springt die App automatisch zum nächsten.
2. **Abo-Modus**, wenn kein Key eingerichtet ist, alle Kontingente leer sind oder das Tageslimit erreicht
   ist: Die App baut den kompletten Auftrag (Regeln + Profil + Stellenanzeige), der Nutzer klickt
   **„Kopieren & Gemini öffnen“** (oder ChatGPT), fügt die Antwort wieder ein – fertig. Die Antwort wird
   genauso geprüft wie eine API-Antwort; ist sie unvollständig, zeigt die App einen Korrektursatz für
   denselben Chat. Gilt für Bewerbung, Lebenslauf-Import und Regel-Korrekturen.

Der Nutzer schickt den Auftrag dabei selbst ab – es wird nichts automatisiert und kein Konto angebunden.

| Kostenloser API-Key | Link |
|---|---|
| Google Gemini | https://aistudio.google.com/apikey |
| Groq | https://console.groq.com/keys |

Hinweis: Bei kostenlosen Angeboten können Anbieter Eingaben zum Training nutzen – die Prompts enthalten
Lebenslaufdaten. Limits ändern sich häufig; aktuelle Werte stehen in den Konsolen der Anbieter.

## Login (ohne Passwort)

1. E-Mail eingeben → **Code senden**
2. 6-stelligen Code aus der Mail eingeben – oder auf den Link in der Mail klicken
3. Fertig. Neue E-Mail-Adressen bekommen automatisch ein Konto (abschaltbar in `branding.json`).
   Die Sitzung gilt 30 Tage, auch nach dem Neuladen der Seite.

Codes sind 10 Minuten gültig, nach 5 Fehlversuchen gesperrt; in der DB liegt nur ein Hash.
Für den Mailversand SMTP in `.env` eintragen (siehe `.env.example`). **Ohne SMTP** zeigt die App den Code
bei lokalem Betrieb (`localhost`) direkt an, sonst steht er in der Server-Konsole.

## Speicherung

Alles liegt lokal in einer Datei: `data/smartresume.db` (SQLite – Profile, Fotos, Bewerbungen inkl. PDFs,
Logins). Kein Cloud-Dienst nötig, Backup = diese Datei kopieren. `data/` ist nicht im Git.

## Funktionen

| Bereich | Was es kann |
|---|---|
| Profil | Lebenslauf (PDF/DOCX/TXT) hochladen → KI liest **einmalig** aus → alles editierbar. Oder manuell eingeben. Foto (auch direkt aus dem PDF), Unterschrift, Skills, Sprachen, Projekte, Stärken mit Beleg, Rahmen (Gehalt, Verfügbarkeit, Studium), eigener Schreibstil, Akzentfarbe. JSON-Export/-Import. |
| Jobs finden | Stellensuche über die Jobbörse der Bundesagentur für Arbeit (kein Konto nötig): Was, Wo, Umkreis, Beschäftigungsart, Zeitraum. Zeigt Gehalt, Homeoffice, Profil-Treffer und „schon beworben“. Optional **KI-Passung** 0–100 % mit Begründung und fehlenden Anforderungen (ein Aufruf für bis zu 25 Stellen). **„Bewerbung erstellen“** übernimmt den kompletten Anzeigentext. |
| Bewerbung | Link (liest JobPosting-JSON-LD der Jobbörsen) oder Text, Beschäftigungsart (Vollzeit, Teilzeit, Werkstudent, Praktikum, Ausbildung, Minijob, Freelance), Zusatz-Skills, Schwerpunkt. |
| Ehrlichkeit | Die KI liefert nur Texte + Referenzen auf Profileinträge; Firmen, Zeiträume, Ausbildung, Gehalt und Eintrittstermin setzt Python aus dem Profil ein. Regel-Check (Übertreibung, Unterverkaufen, erfundene Zahlen, Du/Sie-Mix, Widersprüche) + optionaler KI-Faktencheck + Auto-Korrektur. Fehlende Anforderungen werden angezeigt, aber nie behauptet. |
| Modelle | Gemini, OpenAI-kompatibel (Groq, Mistral, OpenRouter, Ollama …), Claude. Automatischer Wechsel bei Limit/Timeout/Überlastung, zuletzt Abo-Modus. |
| Verwaltung | Nutzer anlegen/löschen, E-Mail ändern, Token-Verbrauch pro Nutzer, Tageslimit für KI-Bewerbungen. |

## Konfiguration

| Datei / Variable | Zweck |
|---|---|
| `.env`, `.env.local` | KI-Keys (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` – einfacher über „KI einrichten“), SMTP. Liegt neben dem Programm bzw. der `.exe`. Gesetzte Umgebungsvariablen haben Vorrang. |
| `branding.json` | Whitelabel: Name, Logo, Farbe, Registrierung/Einladungscode, Tageslimit … (Vorlage: `branding.example.json`) |
| `models.json` | Eigene Modellliste inkl. lokaler Modelle (Vorlage: `models.example.json`). Reihenfolge = Fallback-Reihenfolge. |
| `SMARTRESUME_DB` | Pfad der SQLite-DB (Standard `data/smartresume.db` neben dem Programm) |
| `SMARTRESUME_HOME` | Ordner für `.env`, `branding.json`, `models.json`, `data/` (Standard: Programmordner bzw. Ordner der `.exe`) |
| `SMARTRESUME_INVITE_CODE` | Einladungscode per Umgebung statt in `branding.json` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Versand der Login-Codes |
| `SMARTRESUME_URL` | Öffentliche Adresse für den Login-Link in der Mail (Standard: aus der Anfrage) |

Verbrauch pro Bewerbung: ca. 3.700 Input-Tokens (inkl. komplettem Profil); Lebenslauf-Import einmalig
ca. 2.000–2.600, optionaler Faktencheck ca. 2.200 Tokens.

## Betrieb für mehrere Personen

Am einfachsten betreibt eine Person die App auf einem Rechner oder kleinen Server; alle anderen öffnen nur
den Link und melden sich per E-Mail-Code an. Dafür SMTP eintragen und `SMARTRESUME_URL` setzen.
Startbefehl: `streamlit run app.py --server.port $PORT`. Auf Hostern mit flüchtigem Dateisystem
(z. B. Streamlit Community Cloud) ein persistentes Volume für `data/` nutzen.

## Entwicklung

```bash
python -m pytest            # Unit-, Render- und UI-Tests (Streamlit AppTest, Fake-KI)
pip install pyinstaller && python build_exe.py   # baut dist/SmartResume.exe
```

Ein Tag `v*` (z. B. `git tag v1.0.0 && git push origin v1.0.0`) baut die `.exe` per GitHub Actions und hängt
sie an das Release.

Struktur: `launcher.py` (Start der App/.exe), `smartresume/` (Logik: `auth`, `bridge`, `config`, `paths`, `profile`, `db`, `llm`, `prompts`, `generate`, `quality`,
`cv_import`, `scrape`, `jobsearch`, `render`, `branding`) und `smartresume/ui/` (Seiten). `template.typ` liest alle Inhalte
aus `data.json` – Texte werden nie als Typst-Markup interpretiert. Tests nutzen ein erfundenes Beispielprofil
(`tests/fixtures/`).

## Lizenz

SmartResume steht unter der **GNU Affero General Public License v3.0** (`LICENSE`): Nutzen, verändern und
weitergeben ist erlaubt – wer eine veränderte Version weitergibt oder als Online-Dienst anbietet, muss den
Quellcode dieser Version ebenfalls unter der AGPL veröffentlichen.

Die Schriften in `fonts/` (Lexend, Montserrat, Poppins) stehen unter der SIL Open Font License 1.1
(Lizenztexte im Ordner).
