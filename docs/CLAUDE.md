# CLAUDE.md — SMM Platforma: kodlovchi agent uchun yo'riqnoma

Bu fayl loyiha ildizida turadi. Har bir sessiya boshida o'qiladi. Manba hujjatlar: `docs/TZ.md` (texnik topshiriq), `docs/CONTRACTS.md` (interfeys va ma'lumot shartnomalari). Ziddiyat bo'lsa: **CONTRACTS.md > CLAUDE.md > TZ.md** (CONTRACTS eng aniq). Ziddiyatni topsangiz, jim o'zgartirmang: `docs/DECISIONS.md`ga yozing va foydalanuvchiga ayting.

---

## 1. Loyiha bir jumlada
Agentlik mijozlarining Telegram / Instagram / YouTube akkauntlarini kuzatish, tahlil qilish, kontentni rejalashtirib avtomatik chiqarish, AI bilan plan/ssenariy yaratish va reklama tavsiyalari beradigan ichki platforma. Windows server, lokal tarmoq, `run.bat` bilan ishga tushadi. Interfeys to'liq o'zbek (lotin).

## 2. Qat'iy stek (o'zgartirmang)
Python 3.12 · Django 5 + DRF · Waitress · MySQL 8 (`utf8mb4`) · APScheduler (MySQL jobstore) · React 18 + TypeScript + Vite + Tailwind + TanStack Query + Recharts (SPA, `frontend/`; faqat qurishda Node kerak, ishlashda kerak emas) · aiogram 3 (bot) · Telethon · Meta Graph API · YouTube Data/Analytics/Upload (OAuth) · FFmpeg · PySceneDetect · OpenCV · faster-whisper · ReportLab · openpyxl · cryptography (Fernet) · Argon2.
**Taqiqlangan:** Docker, Celery, Redis, Vue, ORM'siz xom SQL (fon navbat `SKIP LOCKED` bundan mustasno), Selenium/Playwright orqali mijoz akkauntlariga kirish.

## 3. Ish tartibi (har bir vazifa uchun)
1. Vazifaga tegishli CONTRACTS bo'limini o'qing. Shartnomada yo'q narsani o'zingiz o'ylab topmang: avval shartnomaga qo'shishni taklif qiling.
2. **Mock-first:** har bir tashqi xizmat uchun avval `Fake*` (fixture) adapter yozing, keyin real adapter. Butun tizim `USE_FAKES=1` bilan hech qanday kalitsiz ishga tushib, sinab ko'rilishi shart.
3. Kichik, ishlaydigan bo'laklarda ishlang (vertikal bo'lak: model → servis → API → sahifa → test). Yarim tayyor bo'lakni qoldirmang.
4. Har bir bo'lak oxirida: testlar o'tadi, `ruff` va `python manage.py check` toza, `run.bat` yangi muhitda ishlaydi, `docs/PROGRESS.md` yangilangan.
5. Katta qaror (yangi kutubxona, sxema o'zgarishi, shartnoma o'zgarishi) — avval foydalanuvchidan so'rang.

## 4. Strategiya: vertikal bo'laklar
| Bo'lak | Mazmun | Tugash mezoni |
|---|---|---|
| S0 Skelet | loyiha tuzilmasi, `run.bat/stop.bat/autostart.bat`, `.env` ustasi, MySQL, jobs+worker, watchdog, Sozlamalar (shifrlangan), audit | `run.bat` bo'sh mashinada ishlaydi; worker o'ldirilsa qayta tiklanadi |
| S1 Kirish va ruxsat | users, roles, RBAC matritsa, biznesga biriktirish, biznes tanlagich, `PermissionService` | Foydalanuvchi ruxsatsiz biznes/bo'limga serverda ham kira olmaydi (test bilan) |
| S2 Bizneslar | biznes CRUD, andozalar, brend xotirasi (AI'siz qo'lda, versiyalanadi) | |
| S3 O'qish: Telegram + YouTube | connector'lar, provayder qatlami + failover, collector, tarixiy import, metrik jadvallar | Fake va real bilan ishlaydi |
| S4 Dashboard va tahlil | KPI, grafiklar, davr solishtirish, Tizim holati (asosiy), bildirishnomalar (asosiy) | |
| S5 Instagram o'qish + stories tarixi | Meta OAuth, insights, story hourly | Meta tasdig'iga bog'liq bo'lsa Fake bilan yopiladi |
| S6 Raqobatchilar | public scraping, ScrapeCreators, solishtirish | |
| S7 Kontent: kalendar, tasdiqlash, qoidalar | holat mashinasi, vazifalar, Content Rules | |
| S8 Nashr | publish connector'lar, to'g'ridan-to'g'ri upload, R2 zaxira, kill switch | Xato-qayta urinish-idempotentlik testlari |
| S9 Mijoz boti | taklif kodi, hisobot, tasdiq | |
| S10 AI Router + brend AI | router, kalitlar, kvota, cache, "nega ishladi", plan, ssenariy, hook, izoh | |
| S11 Media tahlil | gibrid pipeline | |
| S12 Reklama + Worker havolalar | tavsiya, prognoz, Cloudflare Worker, kliklar | |
| S13 Hisobotlar PDF/Excel + yakuniy | | Qabul mezonlari (TZ 13) |
Bo'laklar tartibini foydalanuvchi bilan kelishmay o'zgartirmang. Bir vaqtda bitta bo'lak.

## 5. Arxitektura qoidalari
- **Adapter naqshi:** tarmoq → `Connector`, ma'lumot manbai → `DataProvider`, AI → `AIProvider`. Biznes mantig'i faqat interfeys bilan gaplashadi, hech qachon `requests.get("https://graph.facebook...")` servis ichida emas. Yangi tarmoq = yangi klass, mavjud kodga tegmaslik.
- **Servis qatlami:** view/API ingichka; mantiq `apps/<app>/services.py`da. Modellarda faqat ma'lumot va oddiy xususiyatlar.
- **Biznes konteksti:** biznesga tegishli har bir model `business` FK va indeksga ega; har bir queryset `BusinessScopedManager.for_user(user)` orqali olinadi. Xom `Model.objects.all()` biznes ma'lumotida **taqiqlangan** (lint qoidasi + test).
- **Metrikalar append-only:** `*_history`, `*_daily`, `*_intraday` jadvallarga faqat INSERT; UPDATE/DELETE yo'q. Dublikat `(platform, external_id)` UNIQUE.
- **Vaqt:** bazada UTC (`USE_TZ=True`), ko'rsatishda `Asia/Tashkent`. Kunlik chegaralarni Toshkent vaqti bo'yicha hisoblang; YouTube kvotasi Pacific vaqti bilan tiklanishini unutmang.
- **Fon ishlari:** hamma uzoq/tashqi ish `jobs` jadvali orqali. View ichida tashqi HTTP chaqiruv, AI chaqiruv, video ishlov **yo'q**. Har bir job **idempotent** bo'lishi shart (qayta ishlasa zarar qilmaydi).
- **Sozlama:** qiymat koddan emas, `system_settings`dan (kalitlar ro'yxati CONTRACTS §12). Kodda faqat sukut qiymat.
- **Konfiguratsiya sirlari:** `.env` ichida faqat `SECRET_KEY`, `FERNET_KEY`, DB parametrlari. Boshqa kalitlar bazada, Fernet bilan shifrlangan.

## 6. Xavfsizlik (buzilmas qoidalar)
1. Instagram/YouTube uchun **login-parol so'ramang, saqlamang**. Faqat OAuth. Bu haqda sozlama yo'q.
2. Telethon: faqat o'qish. `send_message`, `join`, `subscribe`, `delete`, `edit` chaqiruvlari kodda **bo'lmasligi** kerak. `TelethonReadOnlyClient` wrapper'i faqat ruxsat etilgan metodlarni ochadi; testda boshqa metod chaqirish xato berishi tekshiriladi.
3. Tasdiqlanmagan (`approved`dan boshqa) va `AI qoralamasi` bo'lib inson ko'rmagan kontent **hech qachon** nashr qilinmaydi. Nashr servisi buni o'zi ham qayta tekshiradi (UI'ga ishonmaydi).
4. Har bir tashqi so'rov `RateLimiter` va eksponensial backoff'dan o'tadi. 429 yoki blok belgisi → provayder `cooldown`, admin bildirishnomasi.
5. Sirlar (token, kalit, sessiya) bazada faqat shifrlangan; UI'da `••••1234`; loglarda niqoblanadi (`SecretFilter`); AI promptiga **hech qachon** kirmaydi.
6. Server faqat lokal interfeysda tinglaydi (`HOST` sozlamasi). Tashqaridan kiruvchi ulanish yo'q.
7. RBAC server tomonda: har bir view/API `@require_permission(module, action)` + biznes kirishi tekshiruvi. Faqat UI'da yashirish yetarli emas.
8. Parol Argon2, lockout, seans muddati sozlanadi, CSRF/XSS Django vositalari bilan, fayl yuklashda tur va hajm tekshiruvi.
9. Admin o'zini o'chira/ruxsatini kamaytira olmaydi; kamida bitta faol admin.
10. Claude (pullik) API sukut **o'chirilgan**; yoqilmaguncha hech qanday pullik so'rov yuborilmaydi (testi bor).

## 7. AI qoidalari
- Barcha AI chaqiruvlari faqat `AIRouter.run(task_type, ...)` orqali. To'g'ridan-to'g'ri provayder SDK'si chaqirish taqiqlangan.
- Har chaqiruvga brend xotirasining joriy tasdiqlangan versiyasi system kontekst sifatida qo'shiladi; qaysi versiya ishlatilgani `ai_generations`da yoziladi.
- AI faqat taxmin qilmaydi: tahlil javobida raqamli asos (aniq metrikalar) kodda hisoblanib, AI'ga **berib** yuboriladi va javob bilan birga ko'rsatiladi.
- Narx, chegirma, muddat, telefon, manzil AI yozgan matnda faqat biznes ma'lumotidan olinadi; farqi bo'lsa Content Rules "Haqiqiylik" tekshiruvi belgilaydi.
- Natija strukturali (JSON schema) so'raladi va validatsiya qilinadi; yaroqsiz bo'lsa 1 marta qayta so'raladi.
- O'zbekcha til tekshiruvi (CONTRACTS §6.4) o'tmasa yuqoriroq modelga qayta yuboriladi.

## 8. Interfeys qoidalari
- Barcha matnlar o'zbek (lotin), `gettext` orqali `.po` fayllarda; kodda qattiq yozilgan matn yo'q.
- Ranglar: qizil (asosiy) / ko'k / oq; Dark va Light — CSS o'zgaruvchilar (`--brand`, `--brand-2`, `--bg`, `--fg`), Sozlamalardan o'zgaradi.
- Har bir ro'yxat sahifasida: skeleton yuklanish, bo'sh holat matni, aniq xato xabari, saralash va eksport.
- Frontend: `frontend/` (Vite + React + TS). Sahifa view'lari JSON qaytaradi (`apps/web/spa.py`, `ui.py`), React `/app/` da chizadi. Yangi sahifa: view → `spa.respond(kind=...)` → `frontend/src/pages/registry.tsx`. Mijozga hisobot (`report_view.html`) va `offline.html` server-render qoladi.
- Uzoq jarayon uchun progress (job foizi) ko'rsatiladi.
- Yangi ekran qo'shsangiz: ruxsat moduli, menyu elementi, biznes konteksti, 3 holat (yuklanish/bo'sh/xato) bo'lishi shart.

## 9. Kod sifati
- Tip ko'rsatmalari majburiy yangi kodda; `ruff` + `ruff format`; `mypy` interfeys modullarida.
- Testlar: `pytest-django`. Har bir servis uchun birlik test; connector/provayder uchun **kontrakt testlar** (Fake va Real bir xil test to'plamidan o'tadi, real faqat `-m live` belgisi bilan).
- Majburiy test kategoriyalari: RBAC/biznes izolyatsiyasi, kontent holat mashinasi, nashr idempotentligi, failover qoidalari, AI Router almashish va cooldown, Content Rules, kvota hisobi, shifrlash aylanishi.
- Migratsiyalar qaytariladigan, ma'lumotni yo'qotmaydigan bo'lsin. Mavjud migratsiyani tahrirlamang, yangisini qo'shing.
- Logging: JSON-qator, `logs/` ichida aylantirib saqlanadi, `request_id` va `job_id` bilan.
- Windows: yo'llar `pathlib`; `fork` ishlatmang; `.bat` fayllar CRLF; Unicode yo'llarga chidamli.

## 10. Git
- Kichik commit, mazmunli xabar (o'zbek yoki ingliz, bir xil). Bitta commit = bitta mantiqiy o'zgarish.
- `.env`, `*.session`, `media_tmp/`, `logs/` hech qachon commitga tushmaydi (`.gitignore` birinchi commitda).

## 11. Nima qilmaslik kerak
- Spetsifikatsiyada yo'q funksiya qo'shmang ("foydali bo'lar" deb).
- Xato yutib yubormang (`except: pass`). Xato jurnalga, jobda `last_error`ga, kerak bo'lsa bildirishnomaga.
- Test o'tishi uchun testni o'chirmang/yumshatmang.
- Real API'ga test paytida so'rov yubormang (kredit va kvota sarflanadi).
- Sir yoki real mijoz ma'lumotini fixture/repoga qo'ymang.
- Maxfiy qiymatlarni chatga yoki logga chiqarmang.

## 12. Savol berish
Quyidagi hollarda to'xtab so'rang: shartnomada yo'q qaror; xavfsizlik qoidasiga tegadigan o'zgarish; tashqi xizmat hujjati TZ bilan mos kelmasa (masalan, API o'zgargan); bo'lak hajmi ikki baravardan ko'p oshib ketsa.
Qolgan hollarda sukut qiymat tanlab, `docs/DECISIONS.md`ga bir qator yozib, davom eting.

## 13. Hujjatlar
`docs/PROGRESS.md` (bo'laklar holati), `docs/DECISIONS.md` (qarorlar jurnali), `docs/setup/*.md` (Meta, Google, Telegram, R2, Cloudflare Worker, AI kalitlar uchun qadamma-qadam qo'llanmalar, o'zbekcha, skrinshotsiz ham tushunarli).
