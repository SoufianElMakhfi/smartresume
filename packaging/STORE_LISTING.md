# Microsoft Store – Angaben für Partner Center

Alles, was beim Einreichen von SmartResume (Store-ID `9NCM7W2JX4DF`) in Partner Center einzutragen ist.
Texte können direkt kopiert werden.

## Vor dem Einreichen (Checkliste)

- [ ] `PRIVACY.md`: Name und Anschrift eintragen (Platzhalter in Abschnitt 1), committen
- [ ] GitHub-Repo auf **öffentlich** stellen – sonst ist die Datenschutz-URL nicht erreichbar und die AGPL-Zusage
      (Quellcode für Nutzer) nicht eingelöst
- [ ] Datenschutz-URL im Browser ohne Anmeldung öffnen: <https://github.com/SoufianElMakhfi/smartresume/blob/main/PRIVACY.md>
- [ ] Paket bauen: `python build_msix.py --version 2.1.0` (oder GitHub Actions → „Release“ → Run workflow)
- [ ] Als installierte App testen: `packaging/test_install.ps1` (Start aus dem Startmenü, Profil anlegen, PDF
      erzeugen und speichern, Sicherung herunterladen, App schließen und neu öffnen → Daten noch da)
- [ ] Screenshots machen (siehe unten)

## Eigenschaften

| Feld | Wert |
|---|---|
| Kategorie | Produktivität (Unterkategorie, falls gefragt: keine) |
| Datenschutzrichtlinie-URL | `https://github.com/SoufianElMakhfi/smartresume/blob/main/PRIVACY.md` |
| Website | `https://github.com/SoufianElMakhfi/smartresume` |
| Support-Kontakt | `mail@soufian.me` |
| Systemanforderungen | Windows 10 (1809) oder neuer, x64. Microsoft Edge WebView2 (auf Windows 11 und aktuellen Windows-10-Systemen vorinstalliert). Internetverbindung für KI-Funktionen und Jobsuche |
| Produktdeklarationen | **„Diese App nutzt generative KI“ ankreuzen** (siehe unten). Kein Zugriff auf Kamera/Mikrofon. |

## Generative KI (Store-Richtlinie 11.16)

- In Partner Center unter *Produktdeklarationen* die Nutzung generativer KI angeben.
- In der App vorhanden: KI-Hinweis unter jeder fertigen Bewerbung, Knopf **„Unpassenden KI-Inhalt melden“**
  (E-Mail an den Support) und dasselbe unter *Hilfe & Info*.
- Im Beschreibungstext steht der KI-Hinweis (siehe unten, letzter Absatz).

## Begründung für `runFullTrust` (Feld „Beschränkte Funktionen“)

> SmartResume ist eine Desktop-Anwendung in Python (mit PyInstaller gepackt). Beim Start läuft ein lokaler
> Anwendungsprozess, der ausschließlich an 127.0.0.1 gebunden ist, und die Oberfläche erscheint in einem
> eigenen WebView2-Fenster. Die App erzeugt PDF-Dateien, liest vom Nutzer gewählte Lebenslauf-Dateien
> (PDF/DOCX) und speichert Daten lokal. Dafür ist ein voll vertrauenswürdiger Desktop-Prozess nötig
> (Desktop Bridge). Die App installiert keine Dienste oder Treiber, ändert keine Systemeinstellungen und lädt
> keinen Code nach.

## Hinweise für die Zertifizierung (Feld „Hinweise für Zertifizierung“)

> SmartResume does not require an account or an API key to be tested.
> 1. Start the app. It opens its own window. Enter any e-mail address (e.g. test@example.com) and click "Weiter".
>    This creates a local profile on this PC only. No code is sent and no server is involved.
> 2. "Mein Profil": enter a name and one work experience, or upload any CV (PDF/DOCX).
> 3. "Neue Bewerbung": paste any job ad text. Without an AI key the app uses copy & paste mode: it shows a
>    prompt, which you copy into Gemini or ChatGPT in the browser. Then paste the JSON answer back and the app
>    creates the PDF. Optional: "KI einrichten" accepts a free Google Gemini API key (aistudio.google.com/apikey)
>    for fully automatic generation.
> 4. "Jobs finden" searches the public job board of the German Federal Employment Agency (no login).
> The UI is German. All data stays local. Privacy policy and AI-content reporting are under "Hilfe & Info".

## Märkte und Preis

- Preis: **kostenlos**
- Märkte: **Deutschland, Österreich, Schweiz** (optional Liechtenstein, Luxemburg). Die App ist nur auf Deutsch, und
  die Jobsuche nutzt die Bundesagentur für Arbeit.
- Sichtbarkeit: öffentlich

## Altersfreigabe (IARC-Fragebogen)

Kategorie „App (keine Spiele)“. Wahrheitsgemäß beantworten; voraussichtlich:
- Gewalt, Sexualität, Drogen, Glücksspiel, Schimpfwörter: **Nein**
- Nutzer interagieren miteinander / teilen Inhalte mit anderen: **Nein** (alles lokal, kein Austausch)
- Teilt den Standort: **Nein**
- Digitale Käufe: **Nein**
- Uneingeschränkter Internetzugang (Browser): **Nein**. Links öffnen sich im Standardbrowser, die App ist kein Browser.
- Generiert Inhalte mit KI: **Ja**, Bewerbungstexte. Meldeweg vorhanden.

Erwartetes Ergebnis: USK 0 / PEGI 3 (bzw. „Ab 3“).

## Store-Eintrag (Deutsch)

**Produktname:** SmartResume

**Kurzbeschreibung** (max. 200 Zeichen)

> Bewerbungen in Minuten: Anschreiben, Lebenslauf und Deckblatt als PDF – passend zur Stelle, ehrlich formuliert,
> lokal auf deinem PC.

**Beschreibung**

> SmartResume erstellt aus deinem Profil und einer Stellenanzeige eine komplette, maßgeschneiderte Bewerbung:
> Deckblatt, Anschreiben und Lebenslauf als schön gesetztes PDF.
>
> So funktioniert's
> • Lebenslauf hochladen (PDF oder Word) – SmartResume füllt dein Profil automatisch
> • Stellenanzeige einfügen oder den Link angeben – oder direkt in der App nach Jobs suchen
> • Die KI schreibt Anschreiben und Lebenslauf passend zur Stelle; Firmen, Zeiträume und Abschlüsse übernimmt
>   SmartResume unverändert aus deinem Profil
> • ATS-Check: Welche Begriffe der Anzeige fehlen? Mit einem Klick ehrlich ergänzen
> • PDF herunterladen oder direkt aus der App per E-Mail verschicken
> • „Meine Bewerbungen“ behält den Überblick: Status, Notizen, Unterlagen
>
> Ehrlich statt übertrieben
> SmartResume erfindet nichts. Automatische Prüfungen sortieren Floskeln und Übertreibungen aus.
>
> Deine Daten bleiben bei dir
> Kein Konto bei uns, keine Cloud, kein Tracking, keine Werbung. Alles wird lokal auf deinem PC gespeichert;
> Zugangsdaten sind mit Windows verschlüsselt. Mit einer Sicherung nimmst du alles auf einen neuen PC mit.
>
> Kostenlos nutzbar
> Verbinde einen kostenlosen KI-Zugang (z. B. Google Gemini) in zwei Minuten – oder nutze dein eigenes Gemini-
> oder ChatGPT-Konto per Kopieren & Einfügen. Optional auch Mistral, Claude, OpenRouter oder ein lokales Modell.
>
> Hinweis: SmartResume nutzt generative KI. KI kann Fehler machen – bitte lies die Texte vor dem Versand.
> Unpassende Inhalte kannst du in der App melden.

**Funktionen** (Liste, je max. 200 Zeichen)

1. Komplette Bewerbung als PDF: Deckblatt, Anschreiben, Lebenslauf
2. Lebenslauf-Import aus PDF und Word
3. Passgenaue Texte zur Stellenanzeige – ohne erfundene Fakten
4. ATS-Check mit ehrlichen Ein-Klick-Ergänzungen
5. Jobsuche über die Jobbörse der Bundesagentur für Arbeit
6. Versand per E-Mail direkt aus der App
7. Bewerbungen verwalten: Status, Notizen, Unterlagen
8. Alle Daten lokal, verschlüsselte Zugangsdaten, komplette Sicherung
9. Kostenlos mit Google Gemini oder per Kopieren & Einfügen

**Suchbegriffe** (max. 7)

Bewerbung, Lebenslauf, Anschreiben, Bewerbungsschreiben, CV, Jobsuche, KI

**Copyright:** © 2026 Soubasa

## Screenshots (mind. 1, empfohlen 4–6; 1920×1080 oder 1366×768, PNG)

Mit erfundenem Beispielprofil (`tests/fixtures/sample_profile.json` über *Profil-Datei laden*) aufnehmen:

1. Fertige Bewerbung: Downloads und Vorschau des Anschreibens
2. Mein Profil: Fortschritt und Bereiche
3. Neue Bewerbung: Stellenanzeige eingefügt
4. Qualitäts-/ATS-Check
5. Jobs finden: Trefferliste
6. KI einrichten (Gemini kostenlos)

Keine echten Personendaten zeigen.

## Store-Logos

Liegen bereit: `packaging/store-logo-300.png` (300×300) und `packaging/msix/Assets/*`.
Neu erzeugen: `python packaging/make_assets.py`.
