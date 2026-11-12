# Datenschutzerklärung für SmartResume

Stand: 12. November 2026

## 1. Verantwortlicher

[VOR- UND NACHNAME]
[STRASSE UND HAUSNUMMER]
[PLZ ORT]
E-Mail: mail@soufian.me

## 2. Das Wichtigste in Kürze

- SmartResume läuft **vollständig auf deinem PC**. Wir betreiben keinen Server, du brauchst kein Konto bei uns,
  und **wir erhalten keine deiner Daten**.
- Es gibt **keine Werbung, kein Tracking und keine Nutzungsstatistik**.
- Daten verlassen deinen PC nur, wenn du eine Funktion nutzt, die dafür gedacht ist: zum Beispiel wenn eine
  KI deine Bewerbung schreibt, wenn du nach Stellen suchst oder eine Bewerbung per E-Mail verschickst.
  Welche Daten dabei an wen gehen, steht in Abschnitt 4.

## 3. Daten auf deinem PC

SmartResume speichert lokal in einem Ordner deines Windows-Benutzerkontos (in der App unter
*Einstellungen → Daten & Sicherung* angezeigt):

- dein Bewerberprofil: Name, Kontaktdaten, Anschrift, Bewerbungsfoto, Unterschrift, Werdegang, Ausbildung,
  Kenntnisse, Sprachen, Wünsche und Schreibstil sowie der Text eines hochgeladenen Lebenslaufs,
- deine Bewerbungen: Stellenanzeige, erzeugte Texte, PDF, Status und Notizen,
- Einstellungen und, falls eingerichtet, API-Keys und das Passwort deines E-Mail-Kontos. Diese Zugangsdaten
  werden mit Windows (DPAPI) verschlüsselt und sind nur mit deinem Windows-Konto lesbar,
- ein technisches Protokoll (`logs/smartresume.log`) für die Fehlersuche. Es wird bei jedem Start
  überschrieben und nicht übertragen.

Die App setzt im eigenen Fenster ein technisch notwendiges Cookie, damit du angemeldet bleibst. Es verlässt
deinen PC nicht.

**Löschen:** Einzelne Bewerbungen und das Profil kannst du in der App löschen. Beim Deinstallieren löscht
Windows alle Daten der App. Eine Sicherung kannst du vorher unter *Einstellungen → Daten & Sicherung*
herunterladen.

## 4. Wann Daten deinen PC verlassen

### 4.1 KI-Anbieter (nur wenn du einen API-Key einträgst)

Für das Erstellen einer Bewerbung, die Bewertung, wie gut eine Stelle passt, und das Auslesen eines
Lebenslaufs sendet SmartResume Daten direkt von deinem PC an den KI-Anbieter, dessen Key du eingetragen hast:

- **Bewerbung erstellen / Passung bewerten:** Name, berufliche Überschrift, Kurzprofil, Werdegang,
  Ausbildung, Kenntnisse, Sprachen, Schreibstil, deine Zusatzangaben und der Text der Stellenanzeige.
  **Nicht** gesendet werden E-Mail-Adresse, Telefonnummer, Anschrift, Foto und Unterschrift.
- **Lebenslauf auslesen:** der vollständige Text des hochgeladenen Lebenslaufs. Er kann Kontaktdaten
  enthalten.

Mögliche Anbieter, je nach deiner Wahl: Google (Gemini), Groq, Mistral AI, OpenRouter, Anthropic (Claude)
oder ein lokales Modell (z. B. Ollama), bei dem nichts den PC verlässt. Die Verarbeitung richtet sich nach den
Bedingungen und Datenschutzhinweisen des jeweiligen Anbieters, mit dem du selbst einen Vertrag
(API-Nutzungsbedingungen) geschlossen hast. Manche Anbieter verarbeiten Daten außerhalb der EU
(z. B. in den USA). **Bei kostenlosen Angeboten können Anbieter Eingaben zur Verbesserung ihrer Modelle
nutzen.** Die App weist bei der Einrichtung darauf hin.

Rechtsgrundlage: Art. 6 Abs. 1 lit. b DSGVO (du nutzt die Funktion, um deine Bewerbung zu erstellen) bzw.
deine Einwilligung durch das Eintragen des Keys (Art. 6 Abs. 1 lit. a DSGVO).

### 4.2 Kopieren & Einfügen über Gemini oder ChatGPT (ohne API-Key)

Ohne API-Key erzeugt SmartResume einen Auftragstext mit denselben Daten wie in 4.1. **Du** kopierst ihn
selbst in Gemini oder ChatGPT in deinem Browser. Dabei gelten die Bedingungen deines Kontos bei Google bzw.
OpenAI. SmartResume überträgt hier selbst nichts.

### 4.3 Jobsuche

Die Suche nutzt die öffentliche Jobbörse der Bundesagentur für Arbeit (`rest.arbeitsagentur.de`).
Übertragen werden nur deine Suchangaben (Suchbegriff, Ort, Umkreis, Beschäftigungsart, Zeitraum) und
technische Verbindungsdaten wie die IP-Adresse, aber keine Profildaten.

### 4.4 Stellenanzeige per Link laden

Gibst du einen Link zu einer Stellenanzeige ein, ruft SmartResume diese Webseite ab. Der Betreiber der
Webseite erhält dabei technische Verbindungsdaten (IP-Adresse, Zeitpunkt, Browserkennung).

### 4.5 Bewerbung per E-Mail versenden

Wenn du ein E-Mail-Konto einrichtest und eine Bewerbung versendest, verbindet sich SmartResume mit dem
Postausgangsserver deines E-Mail-Anbieters (z. B. Gmail, GMX, WEB.DE) und verschickt die E-Mail mit den
PDFs an die von dir gewählte Adresse.

### 4.6 Links

Links (z. B. zu Gemini, ChatGPT, zur Stellenanzeige oder zu den Seiten der KI-Anbieter) öffnen sich in
deinem Standardbrowser. Dort gelten die Datenschutzhinweise der jeweiligen Seite.

### 4.7 Microsoft Store

Installation und Updates laufen über den Microsoft Store. Dabei verarbeitet Microsoft Daten nach der
[Microsoft-Datenschutzerklärung](https://privacy.microsoft.com/de-de/privacystatement). Wir erhalten von
Microsoft nur zusammengefasste Statistiken, z. B. Downloadzahlen und Absturzberichte ohne Profildaten.

## 5. Kontakt mit uns

Schreibst du uns eine E-Mail (z. B. über *Hilfe & Info → Problem melden*), verarbeiten wir deine Adresse
und den Inhalt nur, um dein Anliegen zu bearbeiten (Art. 6 Abs. 1 lit. b bzw. f DSGVO). Danach löschen wir
die Nachricht, sofern keine Aufbewahrungspflicht besteht. Schick uns bitte keine Bewerbungsunterlagen,
wenn das für dein Anliegen nicht nötig ist.

## 6. KI-erzeugte Inhalte

Anschreiben und Lebenslauf-Texte werden von einer KI erstellt. Fakten wie Firmen, Zeiträume und
Abschlüsse übernimmt SmartResume unverändert aus deinem Profil. Bitte lies die Texte vor dem Versand
trotzdem. Unpassende oder fehlerhafte KI-Inhalte kannst du uns in der App über *Inhalt melden* bzw.
*Hilfe & Info → Problem melden* mitteilen.

## 7. Deine Rechte

Du hast das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung,
Datenübertragbarkeit und Widerspruch (Art. 15–21 DSGVO) sowie das Recht, eine erteilte Einwilligung
jederzeit zu widerrufen. Da deine Daten auf deinem PC liegen, kannst du die meisten dieser Rechte direkt in
der App ausüben. Für Daten bei KI-Anbietern wende dich an den jeweiligen Anbieter. Außerdem kannst du dich
bei einer Datenschutz-Aufsichtsbehörde beschweren.

## 8. Kinder

SmartResume richtet sich an Personen ab 16 Jahren.

## 9. Änderungen

Wenn sich die App ändert, passen wir diese Erklärung an. Es gilt die jeweils aktuelle Fassung, die in der App
unter *Hilfe & Info* und unter
<https://github.com/SoufianElMakhfi/smartresume/blob/main/PRIVACY.md> abrufbar ist.
