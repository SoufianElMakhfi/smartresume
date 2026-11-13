---
name: app-neustart
description: SmartResume lokal (neu) starten, damit der Nutzer den aktuellen Stand sieht. Immer verwenden, wenn die App gestartet, neu gestartet, angezeigt oder nach Code-Änderungen im Browser geprüft werden soll ("starte die App", "ich sehe die Änderung nicht", "Server neu starten", Port 8502).
---

# SmartResume neu starten

Ein einziger Befehl – beendet **alle** alten Server (sonst läuft unbemerkt ein veralteter Stand weiter,
z. B. ein früher im Hintergrund gestarteter), startet neu und prüft, ob die App antwortet:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .claude/skills/app-neustart/neustart.ps1
```

- Ausgabe `OK: http://127.0.0.1:8502 läuft. Stand: <commit> …` → dem Nutzer sagen: Seite neu laden
  (die URL als eigenen Codeblock zum Kopieren).
- Ausgabe `FEHLER: …` → die gezeigte Ursache beheben (Port belegt, .venv fehlt, Fehler im Log), dann erneut.
- Nicht mit `run_in_background` und eigenem `streamlit run` starten: der Prozess hängt sonst an der
  Claude-Sitzung, und ein zweiter Start scheitert an „Port 8502 is not available“.
- Protokoll bei Problemen: `%TEMP%\smartresume-dev.log.err`.
- Fenster-App (pywebview) statt Browser: `.venv\Scripts\python.exe launcher.py` – nur wenn ausdrücklich gewünscht.
