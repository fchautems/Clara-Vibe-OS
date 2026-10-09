@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3.11 -m venv .venv
    if errorlevel 1 py -3 -m venv .venv
  ) else (python -m venv .venv)
  if errorlevel 1 goto failed
)
if not exist ".venv\clara-installed.txt" (
  .venv\Scripts\python.exe -m pip install -r requirements-windows.lock
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install --no-deps -e .
  if errorlevel 1 goto failed
  echo 0.1.0> .venv\clara-installed.txt
)
if not exist "%LOCALAPPDATA%\ClaraVibeOS\setup-complete.json" (
  .venv\Scripts\python.exe -m clara.setup
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -c "import json,pathlib; from clara.config import data_dir; (data_dir()/'setup-complete.json').write_text(json.dumps({'version':'0.1.0'}))"
)
.venv\Scripts\python.exe -m clara.app --fixture %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Preparation ou demarrage interrompu. Le message ci-dessus indique le composant manquant.
pause
exit /b 1
