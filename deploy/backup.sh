#!/usr/bin/env bash
# Kunlik zaxira: DB (manage.py backup) + eski nusxalarni tozalash + (ixtiyoriy) rclone orqali tashqi saqlash.
# crontab:  15 3 * * *  /opt/smm/deploy/backup.sh >> /opt/smm/logs/backup.log 2>&1
set -euo pipefail
cd /opt/smm
./venv/bin/python manage.py backup
find backups -type f -mtime +30 -delete
# Tashqi nusxa (rclone sozlangan bo'lsa): RCLONE_REMOTE=r2:smm-backups
if [ -n "${RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null; then
  rclone copy backups "$RCLONE_REMOTE/db" --max-age 2d
  rclone copy media_store "$RCLONE_REMOTE/media" --max-age 2d
fi
# Zaxira yangiligini tekshirish
newest=$(find backups -type f -mmin -1500 | head -1)
[ -n "$newest" ] || { echo "OGOHLANTIRISH: oxirgi 25 soatda zaxira yo'q!"; exit 1; }
