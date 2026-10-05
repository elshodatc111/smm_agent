@echo off
rem Avtomatik ishga tushish (Task Scheduler) shu faylni chaqiradi. Qo'lda ishlatish shart emas.
cd /d "%~dp0.."
if not exist logs mkdir logs
if exist "tools\service_env.bat" call "tools\service_env.bat"
echo [%date% %time%] service_run boshlandi >> logs\service.log
rem bazani kutish (MySQL xizmati kompyuter yoqilgach biroz kech ishga tushishi mumkin)
".venv\Scripts\python.exe" tools\wait_db.py >> logs\service.log 2>&1
".venv\Scripts\python.exe" manage.py migrate --noinput >> logs\service.log 2>&1
".venv\Scripts\python.exe" tools\supervisor.py >> logs\service.log 2>&1
set "RC=%errorlevel%"
if exist "logs\stop.flag" (
  del /q "logs\stop.flag" >nul 2>&1
  echo [%date% %time%] stop.bat orqali toxtatilgan >> logs\service.log
  exit /b 0
)
echo [%date% %time%] supervisor kutilmaganda tugadi (kod %RC%) >> logs\service.log
exit /b %RC%
