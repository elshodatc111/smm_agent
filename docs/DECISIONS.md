# Qarorlar jurnali

| # | Qaror | Sabab |
|---|---|---|
| 1 | Instagram Login yo'li (Facebook sahifasiz) | Mijoz akkauntiga zarar yo'q, rasmiy OAuth; sahifa bog'lash talab qilinmaydi |
| 2 | Login/parol bilan ulanish taqiqlangan | Akkaunt bloklanish xavfi; Meta/Telegram shartlari |
| 3 | Cloudflare Worker = OAuth callback + havola + vaqtinchalik fayl | Bepul; R2 (karta) shart emas |
| 4 | Video/Reels uchun resumable upload | Rejalashtirilgan video hosting hajmiga bog'liq bo'lmaydi |
| 5 | YouTube OAuth Production + auto-refresh | Testing'da refresh token 7 kunda o'ladi |
| 6 | Telethon: whitelist + SafetyGuard + alohida SIM | Ban oldini olish; faqat o'qish |
| 7 | STT: Groq Whisper → Gemini → lokal Whisper | Tezlik/bepul → sifat → oflayn zaxira |
| 8 | ScrapeCreators: kunlik/oylik/bir-yig'ish limitlari + kesh | Byudjet aniq emas; kredit oqib ketmasin |
| 9 | Navbat MySQL jadvalida (SKIP LOCKED), Redis yo'q | TZ: Docker/Celery/Redis yo'q; Windows |
| 10 | Veb: server-render + HTMX; umumiy `page.html` | Tez yetkazish, bitta joyda uslub; SPA kerak emas |
| 11 | Presetlarda settings/users/system_health yo'q | Eng kam huquq tamoyili (test orqali topildi) |
| 12 | Fake provayderlar `USE_FAKES` da tashqi tarmoqqa chiqmaydi | Demo/test xavfsizligi |
| 13 | `.env` nusxasi zaxira papkasida | Tiklash oson; hujjatda papkani shifrlab saqlash tavsiya etilgan |
| 14 | AI faqat TAKLIF beradi, post yaratmaydi/avto-nashr qilmaydi | Egasi qarori: g'oya va fikrlar, matnni o'zi yozadi |
| 15 | Maqsad har ulanish (akkaunt) uchun, 3 oy, tahrirlanadi; o'zgarishlar `GoalRevision`da | Progress va «qancha qoldi» ko'rsatish |
| 16 | Reklama tahlili: faqat Telegram Ads + Instagram, byudjet yo'q, reklamani targetolog ishga tushiradi; PDF brif | Egasi qarori; platforma reklama ishga tushirmaydi |
| 17 | Faktlar: faqat tasdiqlangan manbalar (RSS), iqtibos manbada bo'lishi shart, raqamli fikr A-manba yoki 2-manba bilan | O'ylab topilgan faktlarning oldini olish |
| 18 | Biznes turlari Sozlamalardan qo'shiladi; har turning o'z pasport maydonlari | Har biznes o'ziga xos |
