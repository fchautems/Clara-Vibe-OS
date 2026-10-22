@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lance d'abord start-clara.cmd pour installer Clara, puis ferme Clara.
  exit /b 2
)
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m clara.journey --screenshots --output "%~dp0resultats-tests\journey.json" %*
exit /b %errorlevel%
