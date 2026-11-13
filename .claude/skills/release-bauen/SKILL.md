---
name: release-bauen
description: Neue SmartResume-Version veröffentlichen bzw. das Store-Paket (.msix) und die SmartResume.exe bauen. Verwenden bei "Release", "neue Version", "exe/msix bauen", "für den Store hochladen", "Version erhöhen" oder wenn dist/ veraltet ist.
---

# Release bauen

Gebaut wird auf GitHub (Workflow `.github/workflows/release.yml`, ausgelöst durch einen Tag `v*`): Tests,
`.exe` mit Selbsttest, `.msix` mit Selbsttest. Lokal bauen nur als Notlösung (unten).

## Ablauf
1. **Stand prüfen:** `git status` sauber, alles auf GitHub. Danach alle Tests: `.venv/Scripts/python -m pytest -q`.
   Rot → abbrechen und melden.
2. **Sicherheit:** dem Nutzer `/security-review` vor dem Release empfehlen (als Codeblock), falls seit dem
   letzten Release größere Änderungen dazugekommen sind.
3. **Version festlegen:** aktuelle Version steht in `smartresume/__init__.py` (`__version__`). Vorschlag machen
   (Fehlerbehebung → x.y.**z+1**, neue Funktionen → x.**y+1**.0) und kurz bestätigen lassen. Der Store verlangt
   für jede Einreichung eine höhere Version als die zuletzt eingereichte.
4. **Version setzen und taggen:**
   ```
   git add smartresume/__init__.py
   git commit -m "Version X.Y.Z"
   git push
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. **Build verfolgen** (dauert ca. 5 Min.):
   ```
   gh run list --workflow release.yml -L 1
   gh run watch <run-id> --exit-status
   ```
   Fehlgeschlagen → `gh run view <run-id> --log-failed`, Ursache beheben, neuen Patch-Tag (Tags nie überschreiben
   oder force-pushen).
6. **Store:** Der Job `publish-store` lädt die geprüfte `.msix` bei jedem Tag automatisch hoch und reicht sie zur
   Zertifizierung ein (Microsoft prüft danach 1–3 Tage). Erfolg prüfen:
   ```
   gh run view <run-id> --log --job publish-store
   ```
   Manuell ohne Tag (Actions → Release → Run workflow): Auswahl `nur Entwurf` (hochladen, im Partner Center
   selbst einreichen) oder `einreichen`.
7. **Fehlt der Store-Zugang** (Job meldet „Store-Zugang fehlt“) → Paket holen und von Hand hochladen:
   ```
   gh run download <run-id> -n SmartResume-msix -D dist
   ```
   Partner Center → App SmartResume → neue Übermittlung → „Pakete“ → `.msix` hochladen → einreichen.
   Texte für die Store-Seite: `packaging/STORE_LISTING.md`.

## Store-Zugang (einmalig)
Repository-Secrets `PARTNER_CENTER_TENANT_ID`, `PARTNER_CENTER_SELLER_ID`, `PARTNER_CENTER_CLIENT_ID`,
`PARTNER_CENTER_CLIENT_SECRET` aus einer Microsoft-Entra-Anwendung mit Rolle „Manager“ (Partner Center →
Kontoeinstellungen → Benutzerverwaltung → Microsoft Entra-Anwendungen). Der Client-Secret läuft ab (max. 2 Jahre)
– dann neuen Schlüssel anlegen und Secret ersetzen. Secrets setzt der Nutzer selbst (Wert nie in den Chat):
```
gh secret set PARTNER_CENTER_CLIENT_SECRET
```

## Notlösung: lokal bauen
Nur wenn GitHub Actions nicht geht. Braucht `pyinstaller` in der .venv und für .msix das Windows SDK (makeappx).
```
.venv/Scripts/python build_exe.py
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/selftest.ps1 dist\SmartResume.exe
.venv/Scripts/python build_msix.py --version X.Y.Z
```

## Wichtig
- Die `.exe` wird **nicht** veröffentlicht – einziger offizieller Download ist der Microsoft Store.
- Neue Datenflüsse seit dem letzten Release? Dann `PRIVACY.md` und ggf. `packaging/STORE_LISTING.md` anpassen.
