@echo off
cd /d "%~dp0"
echo DIQQAT: demo uchun .env faylida USE_FAKES=1 bo'lishi kerak ^(haqiqiy akkauntlarga tegilmaydi^).
".venv\Scripts\python.exe" manage.py seed_demo
pause
