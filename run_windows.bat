@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo PriestBot has not been installed in this folder.
 echo Double-click install_windows.bat from the extracted ZIP once.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 pause
