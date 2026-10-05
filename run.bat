@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMM Platforma
echo ================================================
echo   SMM Platforma - ishga tushirilmoqda
echo ================================================

rem --- 1) Python topish
set "PY="
where py >nul 2>nul && (py -3.12 --version >nul 2>nul && set "PY=py -3.12")
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [XATO] Python topilmadi. Python 3.12 ni python.org dan o'rnating ^(Add to PATH belgisini qo'ying^).
  pause & exit /b 1
)

echo [1/4] Python: %PY%
rem --- 2) Virtual muhit va kutubxonalar
if not exist ".venv\Scripts\python.exe" (
  echo Virtual muhit yaratilmoqda...
  %PY% -m venv .venv || (echo [XATO] venv yaratilmadi & pause & exit /b 1)
)
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist ".venv\.deps_ok" (
  echo Kutubxonalar o'rnatilmoqda ^(birinchi marta 3-10 daqiqa^)...
  "%VPY%" -m pip install --upgrade pip >nul
  "%VPY%" -m pip install -r requirements.txt || (echo [XATO] Kutubxonalar o'rnatilmadi. Internetni tekshiring. & pause & exit /b 1)
  echo ok> .venv\.deps_ok
)

echo [2/4] Kutubxonalar tayyor.
rem --- 3) Birinchi sozlash ustasi
if not exist ".env" (
  "%VPY%" tools\first_run.py || (pause & exit /b 1)
) else (
  "%VPY%" tools\first_run.py || (pause & exit /b 1)
)

echo [3/4] Baza tekshirilmoqda...
rem --- 4) Ishga tushirish (veb + worker, watchdog bilan)
echo.
echo Tayyor. Brauzerda .env dagi PUBLIC_BASE_URL manzilini oching.
echo To'xtatish: stop.bat  yoki bu oynada Ctrl+C.
"%VPY%" tools\supervisor.py
pause
