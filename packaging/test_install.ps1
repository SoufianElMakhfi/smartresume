# Installiert das gebaute Store-Paket (build\msix\stage) als Entwickler-App – ohne Signatur – und startet es.
# So läuft SmartResume genau wie aus dem Store (Paket-Identität, Daten im Paketordner, schreibgeschützter
# Programmordner) und lässt sich vor dem Einreichen testen.
#
# Voraussetzung: Entwicklermodus (Einstellungen → System → Für Entwickler → Entwicklermodus: Ein).
# Vorher bauen:  python build_msix.py
#
#   ./packaging/test_install.ps1            # installieren (bzw. aktualisieren) und starten
#   ./packaging/test_install.ps1 -Remove    # wieder deinstallieren (löscht die Testdaten der App)
param([switch]$Remove)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$manifest = Join-Path $root "build\msix\stage\AppxManifest.xml"
$name = (Get-Content (Join-Path $root "packaging\store.json") -Raw -Encoding UTF8 | ConvertFrom-Json).name

if ($Remove) {
    Get-AppxPackage -Name $name | Remove-AppxPackage
    Write-Host "SmartResume (Test) deinstalliert."
    exit 0
}
if (-not (Test-Path $manifest)) { throw "Kein Paket gefunden – zuerst 'python build_msix.py' ausführen." }
$dev = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock" -ErrorAction SilentlyContinue
if (-not $dev -or $dev.AllowDevelopmentWithoutDevLicense -ne 1) {
    throw "Entwicklermodus ist aus: Einstellungen → System → Für Entwickler → Entwicklermodus einschalten."
}

Add-AppxPackage -Register $manifest -ForceApplicationShutdown
$pkg = Get-AppxPackage -Name $name
Write-Host "Installiert: $($pkg.PackageFullName)"
Write-Host "Daten der App: $env:LOCALAPPDATA\Packages\$($pkg.PackageFamilyName)\LocalCache\Local\SmartResume"
Start-Process "shell:AppsFolder\$($pkg.PackageFamilyName)!SmartResume"
Write-Host ""
Write-Host "Testen: Anmelden, Profil anlegen, Bewerbung als PDF speichern, Sicherung herunterladen,"
Write-Host "Fenster schließen, aus dem Startmenü neu öffnen → noch angemeldet, Daten noch da?"
