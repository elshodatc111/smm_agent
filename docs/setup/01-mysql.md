# 1. MySQL ni o'rnatish va ulash

Tizim ma'lumotlar bazasi sifatida **MySQL 8** dan foydalanadi (sinov uchun SQLite ham bor, lekin real ish uchun MySQL tavsiya etiladi).

## O'rnatish

1. dev.mysql.com/downloads/installer dan **MySQL Installer** ni yuklab oling.
2. «Server only» ni tanlang. Config bosqichida: *Development Computer*, port **3306**, autentifikatsiya — *Use Strong Password Encryption*.
3. `root` uchun parol o'ylab toping va **eslab qoling**. «Start the MySQL Server at System Startup» belgisi yoqilgan bo'lsin.
4. O'rnatish tugagach MySQL xizmat sifatida ishlaydi.

## Baza va foydalanuvchini yaratish

**Oson yo'l:** `run.bat` sozlash ustasi `root` parolini so'raydi va bazani, foydalanuvchini o'zi yaratadi.

**Qo'lda:** MySQL Command Line Client ni oching, `root` parolni kiriting va:

```sql
CREATE DATABASE smm_platform CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smm'@'localhost' IDENTIFIED BY 'KUCHLI_PAROL';
GRANT ALL ON smm_platform.* TO 'smm'@'localhost';
FLUSH PRIVILEGES;
```

Keyin `.env` faylida:

```
DB_ENGINE=mysql
DB_NAME=smm_platform
DB_USER=smm
DB_PASSWORD=KUCHLI_PAROL
DB_HOST=127.0.0.1
DB_PORT=3306
```

## Tekshirish

Loyiha papkasida: `.venv\Scripts\python manage.py doctor` — «Baza (mysql) ulandi» [OK] ko'rinishi kerak.

## Zaxira uchun

`mysqldump` ishlashi kerak (zaxira nusxa shu orqali olinadi). MySQL'ning `bin` papkasini (odatda `C:\Program Files\MySQL\MySQL Server 8.0\bin`) Windows `PATH` ga qo'shing: `Start → "environment variables" → Path → Edit → New`.

## Tez-tez uchraydigan xatolar

- *Can't connect to MySQL server* — MySQL xizmati ishlamayapti: `services.msc` → MySQL80 → Start.
- *Access denied* — `.env` dagi login/parol noto'g'ri.
- *Unknown database* — baza yaratilmagan (yuqoridagi SQL).
