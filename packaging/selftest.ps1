# Selbsttest der gebauten SmartResume.exe. Die .exe ist ein Fenster-Programm (keine Konsole) – deshalb mit
# Start-Process -Wait starten und die Ausgabe über eine Datei holen.
#   ./packaging/selftest.ps1 dist\SmartResume.exe
param([Parameter(Mandatory)][string]$Exe)
$out = Join-Path ([IO.Path]::GetTempPath()) "smartresume-selftest.txt"
$p = Start-Process -FilePath $Exe -ArgumentList "--selftest" -Wait -PassThru -NoNewWindow `
                   -RedirectStandardOutput $out -RedirectStandardError "$out.err"
Get-Content $out, "$out.err" -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch "DEBUG|missing ScriptRunContext" }
if ($p.ExitCode -ne 0) { Write-Error "Selbsttest fehlgeschlagen (Exit-Code $($p.ExitCode))"; exit 1 }
