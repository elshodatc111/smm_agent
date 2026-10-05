@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\stop.py
timeout /t 3 >nul
