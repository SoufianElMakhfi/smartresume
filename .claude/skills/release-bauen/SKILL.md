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
6. **Paket holen:**
   ```
   gh run download <run-id> -n SmartResume-msix -D dist
   ```
   Das Artefakt ist nur 7 Tage verfügbar.
7. **Dem Nutzer die Einreichung häppchenweise erklären** (jeden Schritt einzeln, Kopierbares als Codeblock):
   Partner Center öffnen (`https://partner.microsoft.com/dashboard`) → App SmartResume → neue Übermittlung →
   „Pakete“ → `dist\SmartResume-X.Y.Z.0.msix` hochladen → bei Bedarf Texte aus `packaging/STORE_LISTING.md`
   aktualisieren → „An den Store übermitteln“.

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
