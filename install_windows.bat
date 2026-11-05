@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 installer.py
) else (
  python installer.py
)
if errorlevel 1 (
  echo Installation failed. See update.log in your PriestBot installation folder.
  pause
  exit /b 1
)
echo Installation complete. You can now open PriestBot from your desktop shortcut.
pause
