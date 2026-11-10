@echo off
rem SmartResume starten - Doppelklick genuegt.
rem Beim ersten Start wird alles automatisch eingerichtet (einmalig, 1-3 Minuten).
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto start

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python wurde nicht gefunden.
  echo Bitte installieren: https://www.python.org/downloads/  ^(Haken bei "Add python.exe to PATH" setzen^)
  pause
  exit /b 1
)

echo Erster Start: SmartResume wird eingerichtet ...
%PY% -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto fail

:start
echo SmartResume startet - der Browser oeffnet sich gleich. Dieses Fenster offen lassen.
".venv\Scripts\python.exe" launcher.py
exit /b 0

:fail
echo Einrichtung fehlgeschlagen. Bitte Internetverbindung pruefen und erneut starten.
rmdir /s /q .venv 2>nul
pause
exit /b 1
