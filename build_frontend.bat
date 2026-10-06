@echo off
chcp 65001 >nul
cd /d "%~dp0frontend"
title SMM Platforma - frontend yig'ish
where node >nul 2>nul
if errorlevel 1 (
  echo [XATO] Node.js topilmadi.
  echo O'rnatish: https://nodejs.org saytidan LTS versiyani yuklang, yoki PowerShell'da:
  echo     winget install OpenJS.NodeJS.LTS
  echo So'ng yangi oyna ochib shu faylni qayta ishga tushiring.
  pause & exit /b 1
)
if not exist node_modules (
  echo Kutubxonalar o'rnatilmoqda...
  call npm install || (echo [XATO] npm install bajarilmadi & pause & exit /b 1)
)
echo Yig'ilmoqda...
call npm run build || (echo [XATO] build bajarilmadi & pause & exit /b 1)
echo Tayyor. Endi restart.bat ni ishga tushiring.
pause
