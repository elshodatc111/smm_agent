@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMM Platforma - avtomatik ishga tushish
rem ----- parametr: (bo'sh) = yoqish, remove = o'chirish, status = holat
set "MODE=%~1"
if "%MODE%"=="" set "MODE=install"

rem ----- administrator huquqi bormi? Yo'q bo'lsa o'zi so'raydi
net session >nul 2>&1
if errorlevel 1 (
  echo Administrator huquqi so'ralmoqda... "Ha" ni bosing.
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%MODE%' -Verb RunAs"
  exit /b
)

echo ================================================
echo   SMM Platforma - avtomatik ishga tushish: %MODE%
echo ================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_autostart.ps1" -Root "%~dp0." -Mode %MODE%
echo.
echo O'chirish uchun:  autostart.bat remove     Holatni ko'rish:  autostart.bat status
pause
