@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMM Platforma - dasturlash rejimi
rem Dasturlash rejimi: kod saqlanishi bilan server o'zi qayta yuklanadi (http://127.0.0.1:8001).
rem Frontend (React) ni ham jonli ko'rish uchun Node.js kerak: https://nodejs.org (LTS) yoki: winget install OpenJS.NodeJS.LTS

set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [XATO] .venv topilmadi. Avval run.bat ni bir marta ishga tushiring.
  pause & exit /b 1
)
set DEBUG=1

where node >nul 2>nul
if not errorlevel 1 if exist "frontend\package.json" (
  if not exist "frontend\node_modules" (
    echo Frontend kutubxonalari o'rnatilmoqda ^(birinchi marta^)...
    pushd frontend & call npm install & popd
  )
  echo Frontend dev server: http://127.0.0.1:5173  ^(Django: 8001^)
  start "SMM frontend" /min cmd /c "cd /d %~dp0frontend && npm run dev"
) else (
  echo Node.js topilmadi - frontend tayyor yig'ilgan holda ishlaydi ^(o'zgartirish uchun build_frontend.bat kerak^).
)

echo Django: http://127.0.0.1:8001   ^(to'xtatish: Ctrl+C^)
"%VPY%" manage.py runserver 127.0.0.1:8001
pause
