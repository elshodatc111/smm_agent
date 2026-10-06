# Holat (PROGRESS)

## Bajarilgan (kod + testlar)
Core (shifrlash, sozlamalar, audit, bildirishnoma) · RBAC (modul×amal, biznes kirishi) · Bizneslar + versiyali brend xotirasi · Connector'lar (Telegram, Instagram Login, YouTube, Fake) · Telethon (faqat o'qish, SafetyGuard) · DataProvider + failover (YouTube/ScrapeCreators/t.me) · AI Router (kalit rotatsiyasi, kesh, pullik-gate, o'zbek tili tekshiruvi) · Job navbati + scheduler + worker · Metrikalar/tahlil · Kontent (holat mashinasi, 14 qoida, idempotent nashr, kill switch, vaqtinchalik hosting) · AI studiya · Media tahlil (ffmpeg + STT zanjiri) · Reklama (tavsiya, prognoz) · Hisobotlar (PDF/Excel) · Mijoz boti · Havolalar + Cloudflare Worker · Tizim holati + zaxira · Veb interfeys (React SPA: boshqaruv paneli, kalendar drag-drop, post formasi — formatlash paneli + jonli ko'rinish + fayl tanlash, post statistikasi + AI tahlil, sozlamalar bo'limlari + brend) · Yo'riqnoma (11 bo'lim) · run.bat / watchdog / avtostart / sozlash ustasi · seed_demo.

## Tekshirilgan
- Avtomatik testlar (pytest): hammasi o'tgan (`python -m pytest`).
- Server + worker + watchdog haqiqatan ishga tushirildi (sqlite, USE_FAKES) — sahifa, static, heartbeat javob berdi.

## Faqat soxta (mock) bilan tekshirilgan — haqiqiy kalitlarsiz
Instagram/YouTube/Telegram Bot API/Telethon/Groq/Gemini/OpenRouter/ScrapeCreators/Cloudflare Worker bilan haqiqiy so'rovlar **hali sinalmagan**. Birinchi ulanishda yo'riqnomadagi «Tekshirish» tugmalaridan foydalaning. Ehtimoliy farqlar: API maydon nomlari, Google'ning `workers.dev` redirect URI'ni qabul qilishi, ScrapeCreators endpointlari va javob formati, Meta App Review talablari.

## Ma'lum cheklovlar / keyingi qadam
- MySQL'ga qarshi test o'tkazilmagan (testlar sqlite'da); `SKIP LOCKED` MySQL 8 da ishlaydi, lekin real yuklama ostida sinab ko'rish kerak.
- Frontend o'zgargach `build_frontend.bat` (Node.js 20+ kerak), keyin `restart.bat`. Backend o'zgarsa faqat `restart.bat`.
- Telethon o'rnatish Windows'da `pip install telethon` orqali (requirements'da bor).
- Ko'p tilli interfeys yo'q (faqat o'zbek lotin) — TZ bo'yicha.
