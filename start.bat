@echo off
cd /d "%~dp0"
echo.
echo  ContactForge - HR Contact Finder
echo  Open in browser: http://127.0.0.1:8080
echo  (Port 8000 may be used by another app like SignalHire)
echo.
.venv\Scripts\python.exe run.py
pause
