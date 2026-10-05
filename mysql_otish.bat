@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SQLite - MySQL ko'chirish
if not exist ".venv\Scripts\python.exe" (
  echo [XATO] Avval run.bat ni bir marta ishga tushiring.
  pause & exit /b 1
)
echo Oldin stop.bat ni ishga tushirib, tizimni to'xtating!
pause
".venv\Scripts\python.exe" tools\migrate_to_mysql.py
pause
