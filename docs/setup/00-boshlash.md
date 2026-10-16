# 0. Loyihani ishga tushirish (Windows)

Bu bo'lim loyihani **birinchi marta** o'rnatish va keyin har kuni ishlatish tartibini o'rgatadi. Tizim bitta server kompyuterda (Windows) ishlaydi, boshqa xodimlar esa ofis tarmog'i (LAN) orqali brauzerdan kiradi.

## Nima kerak

| Narsa | Versiya | Qayerdan |
|---|---|---|
| Python | 3.12 | python.org → Downloads. O'rnatishda **Add python.exe to PATH** belgisini qo'ying |
| MySQL Server | 8.x | dev.mysql.com → MySQL Installer (Server only yetarli). Batafsil: 1-bo'lim |
| ffmpeg | so'nggi | ffmpeg.org yoki `winget install Gyan.FFmpeg` — media tahlil uchun |
| Internet | — | kutubxonalar va API'lar uchun |

ffmpeg bo'lmasa ham tizim ishlaydi, faqat «Media tahlil» bo'limi cheklanadi.

## 1-qadam. Loyihani joylashtiring

Loyiha papkasini (`smm_platform`) masalan `C:\SMM\` ichiga ko'chiring. Yo'lda **bo'sh joy va kirill harflar bo'lmasligi** yaxshi.

## 2-qadam. `run.bat` ni ikki marta bosing

Birinchi ishga tushirishda `run.bat` o'zi:

1. Python virtual muhitini (`.venv`) yaratadi va kutubxonalarni o'rnatadi (3–10 daqiqa);
2. **Sozlash ustasini** ishga tushiradi: ma'lumotlar bazasi parametrlari, tizim manzili so'raladi;
3. Maxfiy kalitlarni (`SECRET_KEY`, `FERNET_KEYS`) avtomatik yaratadi va `.env` fayliga yozadi;
4. Baza jadvallarini yaratadi, rollarni yuklaydi;
5. **Administrator** login/parolini so'raydi;
6. Muhit tekshiruvini (`doctor`) ko'rsatadi.

> **Eng muhimi:** usta ekranda ko'rsatgan `FERNET` kalitni alohida joyga (flesh-xotira yoki parol menejeri) nusxalang. Bu kalit yo'qolsa, bazadagi barcha ulanish tokenlari va API kalitlari **qayta tiklanmaydi** — hammasini qaytadan ulashga to'g'ri keladi.

## 3-qadam. Brauzerda oching

Server kompyuterda: `http://localhost:8000`. Boshqa kompyuterlardan: ustada ko'rsatilgan manzil, masalan `http://192.168.1.10:8000`.

Agar boshqa kompyuterdan ochilmasa — Windows Firewall'da 8000-portga ruxsat bering:
`Start → Windows Defender Firewall → Advanced settings → Inbound Rules → New Rule → Port → TCP 8000 → Allow`.
Server kompyuterga routerda **doimiy (statik) IP** biriktiring, aks holda manzil o'zgarib ketadi.

## 4-qadam. Birinchi kirish va tartib

1. Admin login/parol bilan kiring.
2. **Sozlamalar → API kalitlar** bo'limida kerakli kalitlarni kiritasiz (har bir kalitni qanday olish keyingi bo'limlarda).
3. **Bizneslar → Yangi biznes** — biznes ma'lumotini kiriting, so'ng «AI bilan brend yaratish» (AI kalit kiritilgach).
4. **Ulanishlar → Yangi ulanish** — Telegram kanal, Instagram, YouTube.
5. **Foydalanuvchilar** — xodimlarni qo'shing, har biriga biznes va rol biriktiring.

Ketma-ketlik tavsiyasi: avval **Telegram** (eng oson, 10 daqiqa), keyin YouTube, oxirida Instagram (Meta tekshiruvi eng uzoq).

## Sinab ko'rish (kalitlarsiz demo)

Kalitsiz sinash: `.env` faylida `USE_FAKES=1` qilsangiz AI va tarmoqlar soxta rejimda ishlaydi (haqiqiy akkauntlarga hech narsa yuborilmaydi). Demo tugagach `USE_FAKES=0` qiling.

## Har kunlik ishlatish

- **Ishga tushirish:** `run.bat`. Oyna ochiq turishi kerak (yoki avtostart, quyida).
- **To'xtatish:** `stop.bat`.
- **Avtomatik yoqilish:** `autostart.bat` ni *Administrator sifatida* bir marta ishga tushiring — kompyuter yoqilganda tizim o'zi ishga tushadi. Watchdog (kuzatuvchi) veb yoki worker yiqilsa/osilib qolsa qayta ishga tushiradi.
- **Zaxira nusxa:** tizim har kecha avtomatik oladi; qo'lda: `backup.bat`. Batafsil: 9-bo'lim.
- **Yangilash:** yangi versiya fayllarini ustidan ko'chiring (`.env` va `media_store` ga tegmang), `run.bat` ni qayta ishga tushiring — migratsiyalar o'zi bajariladi.

## Tizim qanday ishlaydi (qisqacha)

`run.bat` ikkita jarayon ishga tushiradi: **veb-server** (sahifalar) va **worker** (fon vazifalari: ma'lumot yig'ish, nashr, AI, hisobot, mijoz boti). Ikkalasi bitta baza orqali gaplashadi. Redis/Docker kerak emas. Worker ishlamasa, nashr va yig'ish to'xtaydi — «Tizim holati» sahifasi buni qizil ko'rsatadi.
