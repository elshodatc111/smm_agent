@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MySQL ulanishni tuzatish
if not exist ".venv\Scripts\python.exe" (echo Avval run.bat ni ishga tushiring & pause & exit /b 1)
".venv\Scripts\python.exe" tools\fix_db_user.py
pause
