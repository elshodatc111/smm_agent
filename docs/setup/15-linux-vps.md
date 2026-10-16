# Linux VPS (Ubuntu) ga joylash — GitHub orqali

## 1. Kompyuterda (bir marta)
```
cd "C:\SMM AGENT\smm_platform"
git status          # .env, db.sqlite3, media_store GitHub'ga TUSHMASLIGI kerak (.gitignore)
git add -A && git commit -m "Production tayyor"
git push origin <branch>
```

## 2. Serverda (Ubuntu 22.04/24.04)
```
sudo apt update && sudo apt install -y python3-venv python3-dev build-essential libffi-dev mysql-server nginx ffmpeg git certbot python3-certbot-nginx
sudo useradd -m -d /opt/smm -s /bin/bash smm
sudo -u smm git clone https://github.com/elshodatc111/smm_agent.git /opt/smm
cd /opt/smm && sudo -u smm python3 -m venv venv && sudo -u smm venv/bin/pip install -r requirements.txt
```
MySQL: `sudo mysql` ->
```
CREATE DATABASE smm_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smm'@'localhost' IDENTIFIED BY 'KUCHLI_PAROL';
GRANT ALL ON smm_platform.* TO 'smm'@'localhost'; FLUSH PRIVILEGES;
```
`.env`: `cp .env.example .env` va to'ldiring (SECRET_KEY, FERNET_KEYS, DB_PASSWORD, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, PUBLIC_BASE_URL, HTTPS=1).
Eski bazadan o'tkazsangiz **FERNET_KEYS eski qiymat bo'lishi shart** — aks holda ulangan akkaunt tokenlari ochilmaydi.

```
sudo -u smm venv/bin/python manage.py migrate
sudo -u smm venv/bin/python manage.py bootstrap
sudo -u smm venv/bin/python manage.py createadmin
sudo cp deploy/smm-web.service deploy/smm-worker.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now smm-web smm-worker
sudo cp deploy/nginx.conf /etc/nginx/sites-available/smm && sudo ln -s /etc/nginx/sites-available/smm /etc/nginx/sites-enabled/
# domen nomini nginx.conf da o'zgartiring, so'ng:
sudo nginx -t && sudo systemctl reload nginx && sudo certbot --nginx -d smm.example.uz
sudo -u smm venv/bin/python manage.py doctor
```

## 3. Zaxira (majburiy!)
`crontab -u smm -e` ->  `15 3 * * * /opt/smm/deploy/backup.sh >> /opt/smm/logs/backup.log 2>&1`
Tashqi nusxa uchun rclone sozlab `RCLONE_REMOTE=r2:smm-backups` bering. `.env` dagi FERNET_KEYS ni parol menejerida ham saqlang.

## 4. Yangilash
```
cd /opt/smm && sudo -u smm git pull && sudo -u smm venv/bin/pip install -r requirements.txt \
 && sudo -u smm venv/bin/python manage.py migrate && sudo systemctl restart smm-web smm-worker
```

## 5. Tashqi xizmatlar (domen o'zgargani uchun)
- Meta (Instagram) / Google OAuth redirect URL'lari `PUBLIC_BASE_URL` ga moslab yangilansin. Instagram uchun Meta ilovasi **Live** rejimda bo'lishi kerak.
- Cloudflare Worker (R2) sozlamalari "Cloudflare" bo'limida qayta tekshirilsin.

## Docker varianti
`cp .env.example .env` (DB_PASSWORD, DB_ROOT_PASSWORD qo'shing) -> `docker compose up -d --build`.

## Muammo bo'lsa
`journalctl -u smm-web -u smm-worker -n 100`, `logs/app.log`. Tizim jurnali o'sib ketmaydi (aylantirish yoqilgan).
