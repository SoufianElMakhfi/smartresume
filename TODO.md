# Roadmap

## Offen

- [ ] **Hosting-Anleitung** für den Betrieb mit mehreren Personen (z. B. Docker + kleiner VPS, Railway oder
      Render mit persistentem Volume für `data/`).
- [ ] **Cookie-Login im Browser testen** (AppTest kann keine Cookies): anmelden, Seite neu laden → angemeldet bleiben.
- [ ] **Abo-Modus im Browser testen:** „Kopieren & Gemini/ChatGPT öffnen“ (Zwischenablage braucht HTTPS oder localhost).
- [ ] **Claude und Mistral live testen** (Modell-IDs `claude-haiku-5-5`, `claude-sonnet-5-5`, `mistral-small-latest`).
- [ ] **Gemini Flash** war zeitweise sehr langsam (55–200 s) – Standard ist deshalb Flash-Lite. Neu messen.
- [ ] **Gescannte PDF-Lebensläufe** (nur Bild, kein Text) werden abgelehnt. Idee: PDF direkt multimodal an Gemini.
- [ ] **PDF-Vorschau** in der App (z. B. Seite 1 als PNG via Typst) vor dem Download.
- [ ] **Englische Bewerbungen:** Sprache wählbar machen (Prompts, Labels in `render.py`, Datumsformat).
- [ ] **Weitere PDF-Vorlagen** (z. B. ohne Deckblatt, zweispaltiger CV) als Whitelabel-Option.
- [ ] **Lebenslauf über 1 Seite:** Bei vielen Stationen wird der CV zweiseitig; die App warnt nur, kürzt nicht.
