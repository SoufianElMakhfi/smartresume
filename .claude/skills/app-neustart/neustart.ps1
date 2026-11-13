# Startet den lokalen SmartResume-Server (Streamlit, Port 8502) sauber neu und prüft, ob er läuft.
# Beendet ALLE alten „streamlit run app.py“-Prozesse – sonst läuft unbemerkt ein veralteter Stand weiter.
#   powershell -NoProfile -ExecutionPolicy Bypass -File .claude/skills/app-neustart/neustart.ps1
param([int]$Port = 8502)

$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Output "FEHLER: $py fehlt – zuerst 'SmartResume starten.bat' ausführen (legt .venv an)."; exit 1 }

# 1. Alte Server beenden (venv-Python startet einen zweiten python.exe – beide erwischen)
$old = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -match "streamlit\s+run\s+app\.py" })
foreach ($p in $old) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }

# 2. Warten, bis der Port frei ist
for ($i = 0; $i -lt 20; $i++) {
    if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($busy) {
    $who = (Get-CimInstance Win32_Process -Filter "ProcessId=$($busy.OwningProcess)").CommandLine
    Write-Output "FEHLER: Port $Port ist belegt von PID $($busy.OwningProcess): $who"
    exit 1
}

# 3. Neu starten (eigener, unsichtbarer Prozess; Protokoll im Temp-Ordner)
$log = Join-Path $env:TEMP "smartresume-dev.log"
$env:SMARTRESUME_LOCAL = "1"
Start-Process -FilePath $py -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
    -ArgumentList "-m", "streamlit", "run", "app.py", "--server.port", $Port, "--server.address", "127.0.0.1",
                  "--server.headless", "true", "--browser.gatherUsageStats", "false"

# 4. Prüfen, ob er antwortet
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Port/_stcore/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            $stand = git -C $root log -1 --format="%h %s" 2>$null
            $dirty = if (git -C $root status --porcelain 2>$null) { " + nicht committete Änderungen" } else { "" }
            Write-Output "OK: http://127.0.0.1:$Port läuft. Stand: $stand$dirty. Alte Prozesse beendet: $($old.Count)."
            exit 0
        }
    } catch { }
}
Write-Output "FEHLER: Server antwortet nicht. Letzte Zeilen aus $log.err:"
Get-Content "$log.err" -Tail 15 -ErrorAction SilentlyContinue
exit 1
