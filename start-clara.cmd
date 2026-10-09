@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3.11 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.11 scripts\launch.py %*
  ) else (
    py -3 scripts\launch.py %*
  )
) else (
  python scripts\launch.py %*
)
if errorlevel 1 (
  echo.
  echo Demarrage interrompu. Si Python a pu demarrer, envoyer diagnostic-clara.zip de ce dossier.
  echo Sinon : Python doit etre installe et accessible via py ou python.
  pause
  exit /b 1
)
exit /b 0
