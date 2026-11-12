# SmartResume

Streamlit-App, die aus einem Bewerberprofil und einer Stellenanzeige maßgeschneiderte
Bewerbungsunterlagen erstellt: **Deckblatt → Anschreiben → Lebenslauf** als PDF (Typst).
Mehrbenutzerfähig, Login per E-Mail-Code, Whitelabel über `branding.json`.

**Funktioniert auch ganz ohne API-Key:** Dann entsteht der Text über das eigene Gemini- oder
ChatGPT-Konto des Nutzers (Kopieren & Einfügen, auch mit kostenlosen Konten) – mit denselben Regeln
und Prüfungen wie über die API.

## Schnellstart

**Windows:** SmartResume aus dem **Microsoft Store** installieren (Store-ID `9NCM7W2JX4DF`) – oder
`SmartResume.exe` aus den [Releases](../../releases) in einen eigenen Ordner legen und doppelklicken.

1. SmartResume öffnet sich in einem **eigenen Fenster** (WebView2, kein Browser, keine Konsole).
   Fenster schließen = SmartResume beenden.
2. Mit deiner E-Mail-Adresse anmelden – lokal ohne Code und ohne Passwort.
3. Unter **„KI einrichten“** einen kostenlosen Gemini-Key (optional zusätzlich Groq) einfügen (Link und Anleitung
   stehen dabei), **Testen**, **Speichern** – fertig.

Bei der `.exe` liegen alle Daten (`data/`, `.env`, `logs/`) neben der `.exe`, bei der Store-App im App-Ordner
von Windows (der genaue Ort steht unter *Einstellungen → Daten & Sicherung*). Keys und Mail-Passwörter sind mit
Windows-DPAPI verschlüsselt. Hinweis zur `.exe`: Windows SmartScreen kann bei nicht signierten Programmen warnen
(„Weitere Informationen“ → „Trotzdem ausführen“) – die Store-Version ist signiert.

**Aus dem Quellcode (Windows, macOS, Linux):** Python 3.11+ installieren, dann unter Windows
`SmartResume starten.bat` doppelklicken – oder:

```bash
pip install -r requirements.txt
python launcher.py                   # oder: streamlit run app.py
```

Für die PDF-Erstellung reicht das Python-Paket `typst` (in `requirements.txt`); die Typst-CLI
(`winget install --id Typst.Typst`, `brew install typst`) wird genutzt, wenn vorhanden.

Auf einem Server wird die erste E-Mail-Adresse, die sich anmeldet, **Admin** und landet direkt bei
„KI einrichten“. Lokal (Fenster-App) gibt es keine Admin-/Nutzerverwaltung – jedes Konto darf die KI einrichten.

## KI: API mit automatischem Rückfall auf Gemini/ChatGPT

1. **API-Modelle** mit kostenlosen Keys (Gemini, Groq) oder kostenpflichtigen (Mistral, OpenRouter, Claude) – eingetragen in der App unter
   **„🔑 KI einrichten“** (auf Servern nur Admins; verschlüsselt gespeichert in `.env`). Ist ein Kontingent erschöpft oder ein
   Modell überlastet, springt die App automatisch zum nächsten.
2. **Abo-Modus**, wenn kein Key eingerichtet ist, alle Kontingente leer sind oder das Tageslimit erreicht
   ist: Die App baut den kompletten Auftrag (Regeln + Profil + Stellenanzeige), der Nutzer klickt
   **„Kopieren und Gemini öffnen“** (oder ChatGPT), fügt die Antwort wieder ein – fertig. Die Antwort wird
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
**Lokal** (`SmartResume.exe` bzw. „SmartResume starten.bat“): E-Mail-Adresse eingeben → fertig. Kein Code,
kein Passwort; man bleibt angemeldet, bis man sich abmeldet. Jede Adresse ist ein eigenes Konto auf diesem PC
(mehrere Personen können denselben PC nutzen). Das ist sicher, weil der Launcher die App nur unter
`127.0.0.1` erreichbar macht (`SMARTRESUME_LOCAL=1`) und bei jedem Start ein geheimes Start-Token erzeugt
(`?k=…`, `SMARTRESUME_LOCAL_TOKEN`): Nur das eigene App-Fenster kommt hinein – keine anderen Windows-Konten und
keine Webseite, die `127.0.0.1` anspricht.

**Auf einem Server** (ohne Launcher):
1. E-Mail eingeben → **Code senden**
2. 6-stelligen Code aus der Mail eingeben – oder auf den Link in der Mail klicken
3. Fertig. Neue E-Mail-Adressen bekommen automatisch ein Konto (abschaltbar in `branding.json`).
   Die Sitzung gilt 30 Tage, auch nach dem Neuladen der Seite.

Codes sind 10 Minuten gültig, nach 5 Fehlversuchen gesperrt; in der DB liegt nur ein Hash.
Für den Mailversand SMTP in `.env` eintragen (siehe `.env.example`). **Ohne SMTP** zeigt die App den Code
bei Aufruf über `localhost` direkt an, sonst steht er in der Server-Konsole.

## Speicherung

Alles liegt lokal in einer Datei: `data/smartresume.db` (SQLite – Profile, Fotos, Bewerbungen inkl. PDFs,
Logins). Kein Cloud-Dienst. `data/` ist nicht im Git.
Bei der `.exe` liegt `data/` neben der `.exe`. Die Store-App schreibt nach `%LOCALAPPDATA%\SmartResume`, was
Windows nach `%LOCALAPPDATA%\Packages\<Paket>\LocalCache\Local\SmartResume` umleitet – **beim Deinstallieren
löscht Windows diesen Ordner**. Deshalb gibt es unter *Einstellungen → Daten & Sicherung* eine komplette
Sicherung als ZIP (Profil, Foto, Unterschrift, Einstellungen, alle Bewerbungen mit PDF) und die
Wiederherstellung – auch auf einem neuen PC. Passwörter und KI-Keys sind nicht enthalten.

Datenschutzerklärung: [`PRIVACY.md`](PRIVACY.md) (auch in der App unter *Hilfe & Info*).

## Funktionen

| Bereich | Was es kann |
|---|---|
| Profil | 5 übersichtliche Bereiche mit Fortschrittsanzeige, wird automatisch gespeichert. Skills als Chips (Enter drücken), keine Doppelten. Lebenslauf (PDF/DOCX/TXT) hochladen → KI liest **einmalig** aus → alles editierbar. Oder manuell eingeben. Foto (auch direkt aus dem PDF), Unterschrift, Skills, Sprachen, Projekte, Stärken mit Beleg, Rahmen (Gehalt, Verfügbarkeit, Studium), eigener Schreibstil, Akzentfarbe. JSON-Export/-Import. |
| Jobs finden | Stellensuche über die Jobbörse der Bundesagentur für Arbeit (kein Konto nötig): Was, Wo, Umkreis, Beschäftigungsart, Zeitraum. Erkennt das Fachgebiet und sucht verwandte Begriffe mit (z. B. „Software“ → Softwareentwicklung, Informatik, Developer …); bei Werkstudent/Praktikum werden alle Stellen dieser Art im Umkreis geholt. Unpassendes wird anhand von Titel und Berufsangabe aussortiert, Treffer nach Relevanz sortiert. Zeigt Gehalt, Homeoffice, Profil-Treffer und „schon beworben“. Optional **KI-Passung** 0–100 % mit Begründung und fehlenden Anforderungen (ein Aufruf für bis zu 25 Stellen). **„Bewerbung erstellen“** übernimmt den kompletten Anzeigentext. |
| Bewerbung | Link (liest JobPosting-JSON-LD der Jobbörsen) oder Text, Beschäftigungsart (Vollzeit, Teilzeit, Werkstudent, Praktikum, Ausbildung, Minijob, Freelance), Zusatz-Skills, Schwerpunkt. |
| Versand | E-Mail-Adresse wird aus der Anzeige übernommen (Bewerbungsadresse zuerst). Direkt aus der App senden – mit PDF im Anhang, über das eigene Postfach (einrichten unter Einstellungen: Anbieter wird an der Adresse erkannt, Anleitung je Anbieter – Gmail, GMX, WEB.DE, T-Online, iCloud, Yahoo, Posteo, mailbox.org, freenet oder eigener SMTP). Ohne Einrichtung: **Entwurf mit Anhang** (.eml, öffnet sich in Outlook, Thunderbird, Apple Mail als fertige Mail mit PDF – auch für Outlook/Hotmail-Adressen, die keinen Passwort-Versand mehr erlauben) oder Gmail-Entwurf im Browser. Gesendete Bewerbungen landen in „Meine Bewerbungen“. |
| ATS-Optimierung | Für Bewerbermanagement-Software (Personio, SAP SuccessFactors, Workday …): Die KI nutzt die exakten Begriffe der Anzeige, wo sie laut Profil zutreffen („MS Excel“ statt „Excel“). **ATS-Check** in der Vorschau: Anteil der Schlüsselbegriffe der Anzeige in den Unterlagen, ehrlich erreichbarer Wert, Ein-Klick-Korrekturen (nur für Fähigkeiten aus dem Profil). PDF mit echtem Text, Standard-Überschriften, Name auf jeder Lebenslauf-Seite, Links als lesbarer Text, Titel/Schlüsselwörter in den PDF-Metadaten; Anschreiben und Lebenslauf zusätzlich als getrennte Dateien für Portale. |
| Ehrlichkeit | Die KI liefert nur Texte + Referenzen auf Profileinträge; Firmen, Zeiträume, Ausbildung, Gehalt und Eintrittstermin setzt Python aus dem Profil ein. Regel-Check (Übertreibung, Unterverkaufen, Wiederholungen, erfundene Zahlen, Du/Sie-Mix, Widersprüche) + optionaler KI-Faktencheck + Auto-Korrektur. Fehlende Anforderungen werden angezeigt, aber nie behauptet. |
| Modelle | Gemini, OpenAI-kompatibel (Groq, Mistral, OpenRouter, Ollama …), Claude. Automatischer Wechsel bei Limit/Timeout/Überlastung, zuletzt Abo-Modus. |
| Meine Bewerbungen | Jede erstellte Bewerbung wird automatisch mit Stellenanzeige und PDF gespeichert (Status „Erstellt“); „Als beworben markieren“ setzt nur den Status. Status, Notizen, Download als Mappe oder getrennt (Anschreiben + Lebenslauf), Bearbeiten. |
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
pip install pyinstaller && python build_exe.py   # baut dist/SmartResume.exe (Fenster-Programm)
./packaging/selftest.ps1 dist\SmartResume.exe     # Selbsttest der gebauten .exe (Module, PDF, Startseite)
```

`launcher.py` öffnet ein pywebview-Fenster und startet den Streamlit-Server als Unterprozess (`--server`), der mit
dem Fenster endet. `SMARTRESUME_NO_BROWSER=1` startet nur den Server (gibt die Adresse mit Token aus), Protokoll:
`logs/smartresume.log`. `build_licenses.py` erzeugt beim Build die Lizenzhinweise aller gebündelten Bibliotheken.

Ein Tag `v*` (z. B. `git tag v1.0.0 && git push origin v1.0.0`) baut die `.exe` per GitHub Actions und hängt
sie an das Release.

### Microsoft Store (MSIX)

Der Store signiert die App kostenlos – keine SmartScreen-Warnung. Store-Identität: `packaging/store.json`
(aus Partner Center → Produktidentität), Manifest: `packaging/msix/AppxManifest.template.xml`,
Symbol/Store-Bilder: `python packaging/make_assets.py`.

```bash
python build_msix.py --version 2.0.1    # baut dist/SmartResume-2.0.1.0.msix (braucht makeappx aus dem Windows SDK)
```

Ohne Windows SDK: GitHub → Actions → „Release“ → „Run workflow“; das `.msix` liegt danach unter
„Artifacts“. Hochladen in Partner Center unter „Pakete“; jede Einreichung braucht eine höhere Version.
Texte und Angaben für den Store-Eintrag: [`packaging/STORE_LISTING.md`](packaging/STORE_LISTING.md).
Vor dem Einreichen als installierte App testen: [`packaging/test_install.ps1`](packaging/test_install.ps1).

Struktur: `launcher.py` (Start der App/.exe), `smartresume/` (Logik: `auth`, `bridge`, `config`, `paths`, `profile`, `db`, `llm`, `prompts`, `generate`, `quality`,
`cv_import`, `scrape`, `jobsearch`, `mailer`, `ats`, `render`, `branding`, `secret` (DPAPI), `backup`) und `smartresume/ui/` (Seiten). `template.typ` liest alle Inhalte
aus `data.json` – Texte werden nie als Typst-Markup interpretiert. Tests nutzen ein erfundenes Beispielprofil
(`tests/fixtures/`).

## Lizenz

SmartResume steht unter der **GNU Affero General Public License v3.0** (`LICENSE`): Nutzen, verändern und
weitergeben ist erlaubt – wer eine veränderte Version weitergibt oder als Online-Dienst anbietet, muss den
Quellcode dieser Version ebenfalls unter der AGPL veröffentlichen.

Die Schriften in `fonts/` (Lexend, Montserrat, Poppins) stehen unter der SIL Open Font License 1.1
(Lizenztexte im Ordner). Die Lizenzen aller mitgelieferten Bibliotheken stehen im fertigen Programm unter
*Hilfe & Info* (erzeugt von `build_licenses.py`).
