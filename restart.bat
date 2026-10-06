@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMM Platforma - qayta ishga tushirish
rem Kodga o'zgarish kiritilgandan keyin SHU faylni ishga tushiring: kompyuterni o'chirib yoqish shart emas.
rem Qilinadigan ish: to'xtatish -> baza yangilash -> ishga tushirish -> tayyor bo'lishini kutish -> brauzer.

net session >nul 2>&1
if errorlevel 1 (
  echo Administrator huquqi so'ralmoqda... "Ha" ni bosing.
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [XATO] .venv topilmadi. Avval run.bat ni bir marta ishga tushiring.
  pause & exit /b 1
)

echo ================================================
echo   SMM Platforma - qayta ishga tushirilmoqda
echo ================================================
echo [1/4] To'xtatilmoqda...
"%VPY%" tools\stop.py
timeout /t 3 /nobreak >nul
if exist "logs\stop.flag" del /q "logs\stop.flag" >nul 2>&1

echo [2/4] Baza va statik fayllar tekshirilmoqda...
"%VPY%" manage.py migrate --noinput
if errorlevel 1 (
  echo [XATO] migrate bajarilmadi. Yuqoridagi xabarni o'qing.
  pause & exit /b 1
)

echo [3/4] Ishga tushirilmoqda...
schtasks /query /tn "SMM Platforma" >nul 2>&1
if errorlevel 1 (
  start "SMM Platforma" /min "%VPY%" tools\supervisor.py
) else (
  schtasks /run /tn "SMM Platforma" >nul 2>&1
  if errorlevel 1 start "SMM Platforma" /min "%VPY%" tools\supervisor.py
)

echo [4/4] Tayyor bo'lishi kutilmoqda...
"%VPY%" tools\wait_health.py --open
if errorlevel 1 (
  echo [XATO] Server javob bermadi. logs\serve.out.log va logs\app.log ni ko'ring.
  pause & exit /b 1
)
echo Tayyor.
timeout /t 3 >nul
