@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 (
 echo Python 3.10+ not found. Install Python from python.org and rerun.
 pause
 exit /b 1
)
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
 echo Setup failed. Read any errors above.
 pause
 exit /b 1
)
echo Setup finished. Double-click run_windows.bat.
pause
