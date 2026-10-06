# TEXNIK TOPSHIRIQ (TZ)
## SMM agentlik uchun ichki boshqaruv va tahlil platformasi

| | |
|---|---|
| **Loyiha nomi** | SMM Platforma (ishchi nomi; keyin Sozlamalardan o'zgartiriladi) |
| **Versiya** | 1.0 |
| **Sana** | 2026-10-05 |
| **Ish muhiti** | Windows, bitta server kompyuter, lokal tarmoq, 24/7 doimiy internet (faqat chiquvchi ulanish) |
| **Qamrov** | 1–4-bosqichlar (5-bosqich: yangi tarmoqlar, hozircha qilinmaydi) |
| **Interfeys tili** | To'liq o'zbek tili (lotin) |

---

## 1. UMUMIY MA'LUMOT

### 1.1. Maqsad
Agentlik mijozlarining ijtimoiy tarmoqlarini (Telegram, Instagram, YouTube) bitta joydan kuzatish, tahlil qilish, kontentni rejalashtirish va avtomatik chiqarish, raqobatchilar bilan solishtirish, AI yordamida kontent-plan va ssenariy yaratish hamda reklama (target) bo'yicha sotuvga yo'naltirilgan tavsiyalar berish.

### 1.2. Asosiy tamoyillar
1. **Maksimal bepul:** AI, ma'lumot yig'ish va saqlashda avval bepul variantlar ishlatiladi. Pullik variantlarga o'tish **tayyor, lekin o'chirilgan** holda quriladi va Sozlamalardan yoqiladi.
2. **Mijoz akkauntlari xavfsizligi birinchi o'rinda:** faqat rasmiy API/OAuth, login-parol bilan avtomatlashtirish yo'q, so'rovlar tezligi cheklangan, nashr oldidan tasdiqlash.
3. **Soddalik:** Docker, Celery, Redis yo'q. Bitta `run.bat` butun tizimni ishga tushiradi.
4. **Sozlanuvchanlik:** kalitlar, limitlar, jadvallar, ruxsatlar, provayder ustuvorligi koddan emas, Sozlamalar bo'limidan o'zgaradi.
5. **Biznes konteksti:** sahifadagi barcha ma'lumot tanlangan biznesga tegishli.

### 1.3. Atamalar
- **Biznes:** agentlik mijozi (masalan: o'quv markaz, kiyim do'koni, kompyuter xizmatlari).
- **Ulanish (akkaunt):** biznesga biriktirilgan tarmoq birligi (Telegram kanal, Instagram sahifa, YouTube kanal).
- **Provayder:** tashqi xizmat (Gemini, Groq, OpenRouter, Claude, ScrapeCreators, YouTube Data API va h.k.).
- **Brend xotirasi:** biznes uchun saqlangan AI prompti (ohang, auditoriya, qoidalar).
- **Vazifa (job):** fonda bajariladigan ish (yig'ish, tahlil, nashr).

### 1.4. Qamrovdan tashqari (hozircha)
TikTok, Facebook, LinkedIn va boshqa tarmoqlar; CRM/1C/amoCRM integratsiyasi; zaxira nusxa moduli; xodimlar KPI paneli; mijozlar uchun veb-kirish.

---

## 2. FOYDALANUVCHILAR, ROLLAR VA RUXSATLAR

### 2.1. Foydalanuvchi turlari
| Tur | Kirish usuli |
|---|---|
| **Xodimlar** (admin, menejer, SMM, targetolog, kontent-maker, analitik va admin yaratgan boshqa rollar) | Veb-platforma (lokal tarmoq) |
| **Mijozlar** | **Faqat Telegram bot.** Veb-platformaga kirish huquqi **berilmaydi** |

### 2.2. Boshlang'ich rollar
Admin (yagona, to'liq huquq) · Menejer · SMM mutaxassis · Targetolog · Kontent-maker (dizayner/videograf) · Analitik · Mijoz (faqat bot).

Admin yangi rollarni **o'zi yaratadi**, nomini o'zgartiradi va o'chiradi.

### 2.3. Ruxsatlarni qo'lda belgilash (RBAC)
Admin har bir rol uchun **modul × amal** matritsasini qo'lda belgilaydi.

**Modullar:** Boshqaruv paneli, Bizneslar, Ulanishlar, Raqobatchilar, Tahlil, Kontent kalendar, Nashr (publish), Tasdiqlash, AI studiya, Ssenariylar, Media tahlil, Hook bazasi, Izohlar, Reklama tavsiyalari, Hisobotlar, Havolalar (Worker), Bildirishnomalar, Tizim holati, Sozlamalar, Foydalanuvchilar.

**Amallar:** ko'rish · yaratish · tahrirlash · o'chirish · tasdiqlash · nashr qilish · eksport (PDF/Excel) · sozlash.

- Ruxsatlar rolga beriladi, istisno sifatida alohida foydalanuvchiga ham qo'shish/olib tashlash mumkin.
- Ruxsatlar o'zgarishi darhol kuchga kiradi (qayta kirish talab qilinmaydi).
- Admin o'z huquqini o'chira olmaydi, tizimda kamida bitta faol admin bo'lishi shart.

### 2.4. Bizneslarga biriktirish
- Foydalanuvchi biznesga biriktiriladi: **«Barcha bizneslar»** yoki **tanlangan 1, 2, ... bizneslar**.
- Bir foydalanuvchi turli bizneslarda **turli rol** bilan ishlashi mumkin (masalan, A biznesda SMM, B biznesda faqat Analitik).
- Admin barcha bizneslarni ko'radi.
- Yuqorida **biznes tanlagich** bo'ladi (foydalanuvchida bittadan ko'p biznes bo'lsa). Tanlangach barcha sahifalar faqat shu biznes ma'lumotini ko'rsatadi. Foydalanuvchida «Barcha bizneslar» ko'rinishi (umumiy dashboard) ham bo'ladi.
- Server tomonda har bir so'rov ruxsat + biznes kirishi bo'yicha tekshiriladi (faqat interfeysda yashirish yetarli emas).

### 2.5. Mijoz (Telegram bot) huquqlari
- Mijoz admin yaratgan **bir martalik taklif kodi** orqali botga bog'lanadi va faqat o'z biznesini ko'radi.
- Bir mijozda bir nechta biznes bo'lishi mumkin; bot biznesni tanlash tugmasini ko'rsatadi.
- Mijoz imkoniyatlari: haftalik/oylik hisobot (matn + PDF), asosiy ko'rsatkichlar (obunachi, ko'rish, ER), eng yaxshi postlar, kontent-reja ko'rinishi, rejadagi postni «tasdiqlayman/o'zgartirish kerak» deb belgilash (admin yoqsa), muammo haqida xabar yuborish.
- Admin mijozning bot ruxsatlarini (qaysi bo'limlarni ko'rishi) biznes kesimida sozlaydi, mijozni istalgan vaqtda uzishi mumkin.

---

## 3. TEXNIK ARXITEKTURA

### 3.1. Texnologiyalar
| Qatlam | Tanlov |
|---|---|
| Til | Python 3.12 |
| Backend | Django 5 + Django REST (ichki API) |
| WSGI server | Waitress (Windows) |
| Baza | MySQL 8 (yoki MariaDB), `utf8mb4` |
| Fon ishlari | MySQL'dagi `jobs` jadvali + alohida worker jarayoni |
| Rejalashtirgich | APScheduler (jadval MySQL'da saqlanadi) |
| Frontend | React 18 + TypeScript + Vite + Tailwind (SPA; Node faqat build uchun, ishlashda kerak emas) |
| Grafiklar | ApexCharts |
| Telegram | python-telegram-bot yoki aiogram (bot), Telethon (statistika akkaunti) |
| Instagram | Meta Graph API (rasmiy) |
| YouTube | YouTube Data API v3 + Analytics API + Upload (OAuth) |
| Media | FFmpeg, PySceneDetect, OpenCV, faster-whisper (ixtiyoriy, lokal) |
| Saqlash | Cloudflare R2 (vaqtinchalik nashr fayllari) |
| PDF/Excel | ReportLab (yoki Playwright), openpyxl |
| Shifrlash | cryptography (Fernet), parol: Argon2 |

### 3.2. Ishga tushirish: `run.bat`
`run.bat` quyidagilarni ketma-ket bajaradi:
1. Python va `venv` borligini tekshiradi, yo'q bo'lsa yaratadi.
2. `requirements.txt` o'zgargan bo'lsa kutubxonalarni o'rnatadi.
3. `.env` mavjudligini tekshiradi (yo'q bo'lsa birinchi sozlash ustasini ochadi: baza parametrlari, maxfiy kalit).
4. MySQL ulanishini tekshiradi (portable MySQL varianti tanlansa, uni ham ishga tushiradi), bazani yaratadi.
5. `migrate` ishga tushiradi va boshlang'ich ma'lumotlarni (rollar, sozlamalar) yuklaydi.
6. **Web** (Waitress) va **Worker** jarayonlarini alohida oynalarda/yashirin rejimda ishga tushiradi.
7. Brauzerda platformani ochadi va manzilni (masalan `http://192.168.x.x:8000`) ko'rsatadi.

Qo'shimcha: `stop.bat` (to'xtatish), `autostart.bat` (Windows Task Scheduler'ga kompyuter yoqilganda avtomatik ishga tushirishni qo'shadi), jarayon o'chib qolsa **watchdog** uni qayta ishga tushiradi.

### 3.3. Fon vazifalari (Celery/Redis o'rniga)
- `jobs` jadvali: `id, type, payload, status (pending/running/done/failed/cancelled), priority, attempts, max_attempts, run_at, locked_by, locked_at, last_error, created_at, finished_at`.
- Worker har 2–3 soniyada tayyor vazifani `SELECT ... FOR UPDATE SKIP LOCKED` bilan oladi.
- Qayta urinish: eksponensial kutish (1, 5, 15 daqiqa), so'ng `failed` va bildirishnoma.
- Navbatlar: `collect` (yig'ish), `ai` (AI so'rovlari), `media` (og'ir video ishlari, bir vaqtda 1 ta), `publish` (nashr, eng yuqori ustuvorlik).
- Worker qulab tushsa, «qotib qolgan» vazifalar (`locked_at` eskirgan) avtomatik qayta navbatga qaytadi.
- Bir vaqtdagi ishchi oqimlar soni Sozlamalardan o'zgaradi.

### 3.4. Papka tuzilishi (taklif)
```
smm_platform/
├─ run.bat  stop.bat  autostart.bat
├─ .env
├─ requirements.txt
├─ manage.py
├─ config/                 # Django sozlamalari
├─ apps/
│  ├─ accounts/            # foydalanuvchi, rol, ruxsat
│  ├─ businesses/          # biznes, brend xotirasi
│  ├─ connections/         # ulanishlar (telegram/instagram/youtube)
│  ├─ providers/           # tashqi xizmatlar (collector, failover)
│  ├─ ai_router/           # AI marshrutlash
│  ├─ analytics/           # tahlil, "nega ishladi"
│  ├─ competitors/
│  ├─ content/             # kalendar, nashr, qoidalar
│  ├─ studio/              # plan, ssenariy, hook bazasi, izohlar
│  ├─ media_analysis/
│  ├─ ads/                 # reklama tavsiyalari va prognoz
│  ├─ links/               # Cloudflare Worker boshqaruvi
│  ├─ reports/             # PDF/Excel
│  ├─ tgbot/               # mijoz kabineti va bildirishnomalar
│  ├─ jobs/                # navbat va worker
│  └─ health/              # tizim holati
├─ templates/  static/  media_tmp/  logs/
└─ docs/                   # ulash qo'llanmalari
```

### 3.5. Vaqt zonasi va til
Barcha vaqtlar bazada UTC, ko'rsatishda `Asia/Tashkent`. Sana/son formatlari o'zbek tilida. Interfeys matnlari tarjima fayllarida (`.po`) saqlanadi.

---

## 4. FUNKSIONAL TALABLAR

### 4.1. Bizneslar va Brend xotirasi
- **FR-B1.** Admin biznes yaratadi: nom, logo, faoliyat turi, shahar/hudud, til(lar), qisqa tavsif, mahsulot/xizmatlar, narx oralig'i, maqsadli auditoriya, asosiy maqsad (obuna, lead, sotuv, ko'rish), oylik reklama byudjeti, aloqa ma'lumoti, holati (faol/arxiv).
- **FR-B2.** Faoliyat turi bo'yicha **andozalar**: *o'quv markaz* (lead/ro'yxatga olish, kurs to'lovi, mavsumiylik), *kiyim do'koni* (mahsulot katalogi, aksiya, mavsum, vizual kontent), *kompyuter xizmatlari* (xizmat ishonchi, tez javob, B2B/B2C). Andoza metrikalarni, kontent turlarini va tavsiya mantiqini sozlaydi. Yangi andoza qo'shish mumkin.
- **FR-B3 (Brend xotirasi).** Biznes yaratilganda qisqa ma'lumot kiritiladi → AI **brend profili/system prompt** yozadi (ohang, so'zlashuv uslubi, USP, taqiqlangan so'zlar, tavsiya etilgan hashtaglar, CTA uslubi, auditoriya portreti, kontent ustunlari). Foydalanuvchi uni tahrirlaydi va tasdiqlaydi.
- **FR-B4.** Brend xotirasi **versiyalanadi** (kim, qachon, nima o'zgartirdi; oldingi versiyaga qaytish). Barcha AI chaqiruvlari (plan, ssenariy, caption, izoh javobi, tavsiya) shu promptni tizim konteksti sifatida ishlatadi.
- **FR-B5.** Biznes ma'lumoti o'zgarganda «Brend xotirasini yangilash» taklifi chiqadi.

### 4.2. Ijtimoiy tarmoq ulanishlari
Har bir biznesda har bir tarmoq bo'yicha **1–5 (va undan ko'p)** ulanish; har biri uchun **qo'shish, tahrirlash, o'chirish (arxivlash), vaqtincha o'chirib qo'yish, ulanishni tekshirish** funksiyalari.

**Telegram kanal**
- Bot tokeni bilan ulanadi; bot kanalda admin (to'liq ruxsat) bo'lishi kerak. Tizim ulanishda ruxsatlarni tekshiradi (post yuborish, tahrirlash, o'chirish) va yetishmasa aniq xabar beradi.
- Nashr: bot orqali (matn, rasm, video, albom, tugmalar).
- Statistika: obunachi soni (bot), ko'rishlar, reaksiyalar, ulashishlar, o'sish grafigi (Telethon akkaunti kanalda admin bo'lganda).
- Bir bot bir nechta kanalga ulana oladi.

**Telegram akkaunt (statistika)**
- Telethon sessiyasi (telefon + kod + 2FA bir marta, sessiya shifrlangan saqlanadi).
- **Faqat o'qish** rejimida ishlaydi: tizim bu akkauntdan xabar yubormaydi, guruhlarga qo'shilmaydi.
- Flood-wait'ni hurmat qiladi, so'rovlar orasida tanaffus, kunlik so'rov chegarasi, xatoda avtomatik to'xtash.
- Raqobatchi ochiq kanallar uchun avval ochiq `t.me/s/<kanal>` sahifasi (akkauntsiz) ishlatiladi, yetmasa Telethon.

**Instagram (rasmiy yo'l)**
- Meta Graph API (Instagram Professional akkaunt + Facebook Page + agentlikning Meta Developer app'i). Biznesga ulash: «Instagram'ni ulash» tugmasi → Meta ruxsat oynasi → uzoq muddatli token olinadi, shifrlab saqlanadi, tugashidan oldin avtomatik yangilanadi.
- **Login/parol bilan ulanish ishlatilmaydi** (mijoz akkauntini bloklash xavfi). Bu tizim qarori va Sozlamalarda o'zgartirilmaydi.
- Imkoniyatlar: profil, postlar, reels, stories, izohlar, insights (reach, impressions, saves, shares, profil harakatlari, auditoriya demografiyasi), nashr (rasm, karusel, reels, stories).

**YouTube**
- OAuth 2.0 (Google Cloud Console loyihasi); login/parol yo'q. Kanal egasi brauzerda bir marta ruxsat beradi, refresh token shifrlab saqlanadi.
- Imkoniyatlar: kanal, videolar, shorts, izohlar, Analytics (ko'rish, kuzatish vaqti, CTR, auditoriya, trafik manbalari), video yuklash.
- Eslatma: yangi API loyihalarida yuklangan videolar Google auditidan o'tguncha yopiq (private) bo'lishi mumkin; 6.3-bandga qarang.

**Kelajakka moslik:** har bir tarmoq alohida «connector» klassi (`connect()`, `fetch_stats()`, `fetch_posts()`, `publish()`, `health_check()`), shuning uchun yangi tarmoq qo'shish mavjud kodga tegmaydi.

### 4.3. Ma'lumot yig'ish (collector)
- **FR-C1.** Yig'ish jadvali Sozlamalarda: **sukut bo'yicha kuniga 3–4 marta** (masalan 08:00, 12:00, 17:00, 21:00), test rejimida; keyin tarmoq/biznes/akkaunt darajasida o'zgartiriladi.
- **FR-C2.** O'z akkauntlar rasmiy API'lardan olinadi (kredit sarflamaydi). Raqobatchilar va ochiq ma'lumot provayderlar orqali.
- **FR-C3. Birinchi ulanishda tarixiy import:** oxirgi **3 oy** (kun soni sozlanadi), tezlik cheklangan holda, bajarilish foizi ko'rinadi.
- **FR-C4. Stories:** tarmoq cheklovi tufayli stories insights faqat ~24 soat mavjud. Story chiqqach har soatda statistika olinadi va **bazaga tarix sifatida saqlanadi** (`story_metrics_history`); story tugagach yakuniy ko'rsatkichlar ham yoziladi.
- **FR-C5.** Post metrikalari tarixiy kesimda saqlanadi (1 soat, 6, 24, 72 soat, 7, 30 kun), ya'ni «o'sish egri chizig'i» tahlil qilinadi.
- **FR-C6.** Har bir yig'ishning natijasi, sarflangan kredit/kvota va xatosi jurnalga yoziladi.
- **FR-C7.** Dublikatlar `(platform, external_id)` bo'yicha oldi olinadi.

### 4.4. Provayderlar va avtomatik almashtirish (failover)
**Provayder qatlami:** har bir ma'lumot turi (profil, postlar, video ro'yxati, izohlar, transkript) uchun bir nechta provayder ro'yxati va ustuvorlik tartibi bo'ladi.

**YouTube raqobatchi/ochiq ma'lumot: YouTube Data API ⇄ ScrapeCreators**
- Ikkalasi ham maksimal ishlatiladi. Ustuvorlik Sozlamalardan (sukut: avval Data API, chunki bepul).
- **Avtomatik almashtirish qoidalari:**
  - Data API `quotaExceeded` yoki kunlik kvota chegarasi (sozlanadi, masalan 90%) → ScrapeCreators'ga o'tish.
  - ScrapeCreators krediti tugasa yoki «ogohlantirish chegarasi»dan past bo'lsa → Data API'ga o'tish.
  - Ikkalasi ham tugasa → vazifa ertasi kunga qoldiriladi (Data API kvotasi Tinch okeani vaqti bilan yarim tunda tiklanadi) + admin'ga bildirishnoma.
  - Provayder qayta tiklanganda ustuvorlik avtomatik qaytadi.
- Kvotani tejash: javoblar keshlanadi, o'zgarmagan ma'lumot qayta so'ralmaydi, faqat yangi postlar batafsil olinadi.

**ScrapeCreators**
- Rejim: **Bepul (test)** / **Pullik**. Hozir bepul rejim; pullik rejimga o'tish Sozlamalarda bitta tugma bilan (yangi API kalit yoki qo'shimcha kredit sotib olingach).
- Kredit hisobi: har so'rovdan keyin sarf yoziladi, qoldiq ko'rsatiladi, **sarfni oldindan hisoblagich**: «bu jadval bilan kredit necha kunga yetadi».
- Himoya: har bir yig'ish uchun kredit chegarasi (per-run cap), kunlik va oylik chegara, `cache_max_age` parametri orqali keshdan foydalanish (kesh javobi kredit sarflamaydi), chegaraga yetganda to'xtash va xabar berish.
- **Muhim ogohlantirish:** bepul rejimda faqat boshlang'ich kreditlar beriladi. «Kuniga 3–4 marta» yig'ish raqobatchilar soniga ko'paytirilsa, kredit tez tugaydi. Shuning uchun test rejimida: raqobatchilar uchun kuniga 3–4 marta faqat *engil* so'rovlar (profil), og'ir so'rovlar (postlar ro'yxati, transkript) kamroq, hamma narsa Sozlamalarda o'zgartiriladi.
- Provayder kaliti almashtirilganda yoki yangi provayder qo'shilganda kod o'zgarmaydi (adapter interfeysi).

### 4.5. Tahlil moduli
- **FR-A1.** Har bir ulanish uchun: obunachi dinamikasi, ko'rishlar, ER (engagement rate), reach, like/izoh/saqlash/ulashish, post chastotasi, eng yaxshi/yomon kontent, kontent turi bo'yicha samaradorlik, eng yaxshi vaqt/hafta kuni, hashtag va mavzu tahlili.
- **FR-A2.** Davrlar: kun / hafta / oy / tanlangan oraliq; avvalgi davr bilan solishtirish.
- **FR-A3. «Nima uchun bu post ishladi?»:** post tanlanganda AI quyidagilarni tahlil qiladi: vaqt, format, davomiylik, hook, mavzu, CTA, caption uzunligi, hashtaglar, vizual xususiyatlar; biznes o'rtachasi bilan taqqoslab, sababni **tushuntirib** va **takrorlash tavsiyasi** bilan beradi. Raqamli asos (aniq metrikalar) AI matni bilan birga ko'rsatiladi, ya'ni AI faqat taxmin qilmaydi.
- **FR-A4. Anomaliya:** keskin o'sish/pasayish aniqlanganda bildirishnoma.
- **FR-A5. Sotuvga yo'naltirilgan tahlil:** tarmoq ko'rsatkichlarini maqsadga (lead/sotuv) bog'lash: UTM/havola kliklari, promo-kod, qo'lda kiritilgan lead va sotuvlar (CRM integratsiyasi keyinga qoldirilgan).
- **FR-A6.** Tahlil sarlavhalari soddalashtirilgan o'zbek tilida, «nimani o'zgartirish kerak» xulosasi bilan tugaydi.

### 4.6. Raqobatchilar
- Telegram kanallar va Instagram sahifalar uchun majburiy; YouTube uchun ham ishlaydi.
- Biznes uchun raqobatchilar ro'yxati (nom, tarmoq, havola); har birining ochiq metrikalari tarixiy saqlanadi.
- Solishtirish: obunachi o'sishi, post chastotasi, o'rtacha ko'rish/ER, eng yaxshi postlar, kontent turlari, e'lon vaqti.
- AI xulosasi: raqobatchi nimani yaxshi qilmoqda, biznes qayerda orqada, qaysi mavzu/format bo'sh qolgan (kontent bo'shlig'i).
- Raqobatchi hooklari va yaxshi ishlagan postlar **Hook bazasi**ga taklif sifatida tushadi (nusxa ko'chirmaslik qoidasi bilan, 4.8-band).

### 4.7. Kontent kalendar va nashr
- **FR-K1.** Kalendar (oy/hafta/kun ko'rinishi), tarmoq va biznes filtrlari. Post, reels/shorts, uzun video, stories, karusel, Telegram post turlari.
- **FR-K2.** Kontent holatlari: *Qoralama → Tasdiqlash kutilmoqda → Tasdiqlandi → Rejalashtirildi → Nashr qilinmoqda → Chiqarildi / Xato*.
- **FR-K3.** Vazifa tayinlash: mas'ul (SMM, kontent-maker), muddat, izoh; holat o'zgarganda bildirishnoma.
- **FR-K4. Tasdiqlash oqimi:** SMM yaratadi → menejer (yoki huquqli rol) tasdiqlaydi → rejalashtirilgan vaqtda avtomatik chiqadi. Tasdiqlanmagan kontent **hech qachon** avtomatik chiqmaydi. Biznes uchun mijoz tasdig'i (Telegram bot orqali) ixtiyoriy yoqiladi.
- **FR-K5. Avtomatik nashr** (Telegram, Instagram, YouTube): rejalashtirilgan vaqtda worker bajaradi.
- **FR-K6. Cloudflare R2 vaqtinchalik saqlash:**
  1. Fayl nashrdan oldin (sozlanadigan vaqt, masalan 30–60 daqiqa) R2'ga yuklanadi (Instagram Graph API videoni ochiq URL'dan oladi).
  2. Nashr muvaffaqiyatli bo'lgach (barcha tarmoqlarda) fayl R2'dan **avtomatik o'chiriladi**.
  3. R2'dagi jami hajm hech qachon **9 GB**dan oshmaydi (10 GB bepul limit zaxirasi). Yuklashdan oldin hajm tekshiriladi; joy yetmasa vazifa navbatda kutadi va admin'ga xabar boradi.
  4. Xatoda fayl N soat (sozlanadi) saqlanadi, so'ng tozalanadi. Tozalash vazifasi muntazam ishlaydi, «yetim» fayllar topilsa o'chiriladi.
  5. Asl fayllar server diskida kontent-maker yuklagan holda qoladi (saqlash muddati sozlanadi).
- **FR-K7. Instagram:** nashr konteyner yaratish → tayyorlikni kutish → nashr tartibida; kunlik nashr limitlariga rioya qilinadi. Stories nashri qo'llab-quvvatlanadi.
- **FR-K8. YouTube avtopost:** video yuklash (sarlavha, tavsif, teglar, maxfiylik, rejalashtirilgan vaqt, miniatyura). Yuklash kvotasi qimmat, shuning uchun kunlik yuklash soni kvota bo'yicha hisoblanib cheklanadi. Audit holati 6.3-bandda.
- **FR-K9. Xavfsizlik:** nashrdan oldin «quruq tekshiruv» (formatlar, o'lcham, davomiylik, caption uzunligi, ruxsatlar); xatoda qayta urinish (maksimal 3), takroriy nashrning oldini olish (idempotentlik kaliti); har bir biznes va tarmoq uchun **«Avtonashrni to'xtatish»** (kill switch).
- **FR-K10.** Nashrdan keyin natija (havola, ID) saqlanadi va statistika yig'ish jadvaliga qo'shiladi.

### 4.8. Kontent qoidalari (Content Rules)
Har bir AI yaratgan yoki qo'lda yozilgan kontent nashrdan oldin qoidalar dvigatelidan o'tadi. Qoidalar biznes darajasida sozlanadi:
1. **Brend qoidalari:** ohang, taqiqlangan/majburiy so'zlar, CTA shakli, emoji darajasi.
2. **Tarmoq qoidalari:** matn uzunligi, hashtag soni, video nisbati va davomiyligi (Reels/Shorts/Stories), fayl hajmi.
3. **Haqiqiylik:** narx, chegirma, muddat, aloqa ma'lumotlari faqat biznes ma'lumotlaridan olinadi; AI uydirgan raqam/va'dalar belgilanadi.
4. **Originallik:** raqobatchi matnidan nusxa ko'chirishga yo'l qo'yilmaydi (o'xshashlik tekshiruvi), Hook bazasidan faqat g'oya/tuzilma olinadi.
5. **Tarmoq siyosatlari:** spam, yolg'on da'volar, sog'liq/moliya bo'yicha ehtiyotkor ibora, mualliflik huquqi (musiqa/rasm) ogohlantirishlari.
6. **Til:** o'zbekcha imlo va uslub tekshiruvi; AI yozgan matn «AI qoralamasi» deb belgilanadi va **inson ko'rib chiqmaguncha** nashrga chiqmaydi.
- Natija: *O'tdi / Ogohlantirish / To'xtatildi*, aniq sabab bilan. «To'xtatildi» holatida nashr bloklanadi, ogohlantirishda ma'lumot berilib, huquqli foydalanuvchi tasdiqlashi mumkin.

### 4.9. AI studiya
- **FR-S1. Oylik kontent-plan** (har bir tarmoq uchun alohida): tahlil + brend xotirasi + raqobatchi tahlili + andoza asosida; kunlar, format, mavzu, hook g'oyasi, CTA, maqsad, mas'ul. Rejani bir tugma bilan kalendarga «qoralama» sifatida yuklash.
- **FR-S2. Ssenariy generatori:** formatlar: Reels/Shorts, uzun YouTube video, reklama roligi, podkast, stories ketma-ketligi. Tuzilma: hook (birinchi 3 soniya), sahnalar, ovozli matn, ekrandagi matn, kadr/kompozitsiya tavsiyasi, CTA, davomiylik, kerakli rekvizit. Variantlar (A/B hook).
- **FR-S3. Ssenariy tahlili:** yozilgan/yuklangan ssenariy baholanadi: hook kuchi, tuzilma, sur'at, davomiylikka mosligi, CTA aniqligi, brend ohangiga mosligi, sotuv yo'nalishi; ball + aniq tuzatish takliflari.
- **FR-S4. Caption va hashtag** generatori, tarmoq qoidalariga mos.
- **FR-S5. Hook bazasi:** o'z va raqobatchi postlaridan eng yaxshi ishlagan hooklar (matn, format, natija, mavzu, biznes turi) saqlanadi, teglanadi, qidiriladi; ssenariy yozishda ilhom sifatida taklif qilinadi.
- **FR-S6. Izohlarga javob tavsiyalari:** o'z akkauntlardagi izohlar yig'iladi, sentiment (ijobiy/neytral/salbiy) va turi (savol, shikoyat, sotuv niyati) aniqlanadi, brend ohangida **javob qoralamasi** tavsiya etiladi. Javob xodim tasdig'idan keyin yuboriladi. Avtomatik javob yo'q. Salbiy/shikoyat izohlar haqida bildirishnoma.
- **FR-S7.** Barcha AI natijalari tarixda saqlanadi, qaysi model/provayder ishlatgani ko'rinadi; natijani qayta yaratish, tahrirlash, kalendarga yuborish mumkin.

### 4.10. Media tahlil (gibrid)
Yuklangan yoki nashr qilingan video/rasm tahlili **gibrid** pipeline bilan:
1. **Lokal (CPU/GPU):** FFmpeg orqali metadata (davomiylik, nisbat, FPS), PySceneDetect bilan sahnalar, 8–16 ta asosiy kadr, audio ajratish, sahna almashish tezligi, yuz borligi (OpenCV), ranglar, kadrdagi matn (ixtiyoriy OCR).
2. **Audio → matn:** ustuvorlik Groq Whisper (bepul), zaxira lokal faster-whisper (`small/medium`, int8; GTX 1660 Super uchun optimallashgan).
3. **Bulutli AI (Gemini):** asosiy kadrlar + transkript + metadata **bitta so'rov**da yuboriladi → hook, vizual sifat, sur'at, CTA, brend mosligi, yaxshilash takliflari.
4. **Natija keshlanadi** (fayl xeshi bo'yicha), bir fayl ikki marta tahlil qilinmaydi.
- Faqat yangi postlar tahlil qilinadi (tarixiy import uchun 3 oy chegarasi), uzun videolar `media` navbatida bittadan ishlaydi; navbat holati va taxminiy vaqt ko'rinadi.
- Muvaffaqiyat mezoni: 30–60 soniyalik video uchun odatiy tahlil ~1–2 daqiqa (navbat kutishisiz).
- Bulutli AI mavjud bo'lmasa, qisqartirilgan lokal tahlil (metadata + transkript + oddiy ko'rsatkichlar) bajariladi.

### 4.11. AI Router
- **Provayderlar:** Gemini (Google AI Studio), Groq, OpenRouter (bepul modellar); keyinchalik **Claude API** (hozir **o'chirilgan**, kalit kiritilganda va yoqilganda ishlaydi).
- Admin API kalitlarni **Sozlamalar**dan bir marta kiritadi (shifrlangan saqlanadi). Har bir provayder uchun bir nechta kalit qo'shish mumkin (aylantirib ishlatiladi).
- **Vazifa → ketma-ketlik** jadvali sozlanadi. Boshlang'ich taklif:

| Vazifa turi | Ustuvorlik |
|---|---|
| O'zbekcha uzun matn (plan, ssenariy, tahlil xulosasi) | Gemini → OpenRouter (bepul) → Groq → *(Claude, o'chirilgan)* |
| Tez tasniflash (sentiment, izoh turi, teglar) | Groq → Gemini Flash → OpenRouter |
| Rasm/kadr tahlili | Gemini → *(Claude)* |
| Audio → matn | Groq Whisper → lokal faster-whisper |
| Brend profili yaratish | Gemini → OpenRouter → *(Claude)* |

- **Avtomatik almashish:** `429/quota/timeout/5xx` xatoda keyingi kalitga/provayderga o'tadi; muvaffaqiyatsiz kalit «sovitish» (cooldown) vaqtiga tushadi.
- **Kvota hisobi:** har bir kalit/model bo'yicha so'rovlar, tokenlar, xatolar, kunlik/minutlik limit (admin kiritadi yoki avtomatik aniqlanadi); limitga yaqinlashganda ogohlantirish va yumshoq to'xtatish.
- **Tejash:** natija keshi (bir xil kiritish = qayta so'ramaslik), qisqa promptlar, kunlik bepul limit uchun ustuvorlik navbati (nashrga aloqador vazifalar birinchi), og'ir ishlarni tunga ko'chirish imkoniyati.
- **Pullik rejimga o'tish (tayyor ulangan):** Sozlamalarda «Claude API yoqish» + oylik byudjet chegarasi + qoidalar («faqat bepul hammasi tugaganda», «faqat murakkab vazifalar uchun», «doim»). Yoqilmaguncha hech qanday pullik so'rov yuborilmaydi.
- **Til sifati:** o'zbekcha natija sifati past model bilan qaytsa (til tekshiruvi), yuqoriroq modelga qayta yuboriladi.
- Foydalanuvchi so'rovlarining maxfiy ma'lumotlari (parol, token) AI'ga hech qachon yuborilmaydi.

### 4.12. Reklama tavsiyalari va sotuv prognozi
**Maqsad:** kiritilgan byudjet doirasida sotuvni maksimal oshiradigan reklama takliflari, qaysi postga **qachon** target yoqish va taxminiy kutiladigan natija.

**Kiritiladigan ma'lumotlar (biznes darajasida):** oylik/kampaniya byudjeti, maqsad (lead/sotuv/obuna), o'rtacha chek yoki kurs narxi, lead→sotuv konversiyasi (boshida taxminiy, keyin haqiqiy ma'lumotdan yangilanadi), marja (ixtiyoriy), hudud va auditoriya.

**Tizim nima qiladi:**
1. **Reklama nomzodlarini topadi:** organik ko'rsatkichi yuqori (ER, saqlash, ulashish, kuzatish vaqti) post/video/reelslarni va kanal bo'yicha o'sish nuqtalarini ajratadi, chunki aynan ularni kuchaytirish arzonroq.
2. **Vaqt bo'yicha tavsiya:** postdan keyin qachon (masalan, dastlabki 24–72 soatdagi ko'rsatkich ma'lum bo'lgach), hafta kuni/soatda va mavsumiy (aksiya, ro'yxatga olish davri) kontekstda yoqishni taklif qiladi.
3. **Byudjetni taqsimlaydi:** tarmoq/kampaniya/post bo'yicha taqsimot taklifi (tarixiy samaradorlik asosida), test va masshtablash bosqichlari.
4. **Kampaniya loyihasi:** maqsad, auditoriya (yosh, hudud, qiziqish), joylashuv, matn variantlari, kreativ tavsiyasi, kunlik byudjet, to'xtatish qoidasi (masalan, lead narxi X dan oshsa).
5. **Taxminiy sotuv prognozi:** uch stsenariy (past / o'rtacha / yuqori). Hisob shaffof: *byudjet → taxminiy ko'rsatuvlar/kliklar (o'z tarixi va andoza ko'rsatkichlar bo'yicha) → lead → sotuv → tushum va ROI*. Har bir qadamdagi faraz va uning manbasi ko'rsatiladi. Prognoz **taxminiy** ekani aniq yoziladi; real natija kiritilgach model o'z biznesiga moslashadi (kalibrovka).
6. **Kampaniya natijasi:** haqiqiy sarf va natija kiritiladi (yoki import qilinadi) → rejaga nisbatan farq tahlili → keyingi tavsiyalar.

**Telegram Ads (`ads.telegram.org`):** tizim rejalashtirilgan postga mos **reklama matni** (platforma cheklovlariga rioya qilgan holda), maqsadli kanal/mavzu/auditoriya, taklif narxi va byudjet tavsiyasini tayyorlaydi. Kampaniyani targetolog kabinetda yaratadi; sarf va natijalar tizimga qo'lda yoki CSV orqali kiritiladi. (Telegram Ads kampaniya boshqaruvi uchun ochiq API mavjudligi tasdiqlanmagan; aniqlansa, keyingi versiyada ulanadi.)

**Instagram target (Meta Ads):** 1–4-bosqichda **tavsiya + kampaniya loyihasi** rejimi. Meta Marketing API orqali kampaniyani to'g'ridan-to'g'ri yaratish alohida modul (qo'shimcha ruxsatlar: Business Manager, ad account, to'lov usuli) sifatida **ixtiyoriy kengaytma** hisoblanadi.

**Targetolog roli:** o'ziga biriktirilgan bizneslarning tavsiyalari, byudjet va natijalarini boshqaradi.

### 4.13. Cloudflare Worker (havolalar va klik hisobi)
- Server tashqaridan ko'rinmagani uchun qisqa havolalar va klik hisobi **Cloudflare Worker** orqali ishlaydi (bepul limit doirasida).
- Tizimdan boshqaruv (Cloudflare API tokeni bilan): qisqa havola yaratish (nishon URL, UTM parametrlari, biznes/post/kampaniya bilan bog'lash), tahrirlash, o'chirish/o'chirib qo'yish, amal qilish muddati.
- **Ko'rish:** Worker holati (ishlayapti/xato), so'rovlar soni va bepul limitga nisbati, havolalar ro'yxati, kliklar (vaqt, manba, qurilma turi darajasida umumiy), eng yaxshi havolalar.
- Klik ma'lumotlari Worker xotirasidan (KV/D1) muntazam tizimga olinadi va bazaga saqlanadi. Tahlilda post/kampaniya → kliklar → lead bog'lanadi.
- Worker kodi loyiha ichida tayyor shablon sifatida beriladi, tizim uni joylashtirishda yordam qiladi (yoki aniq qo'llanma).
- Qo'lda kiritiladigan **lead va sotuvlar** (sana, manba/havola, summa) hisobotlarga qo'shiladi.

### 4.14. Hisobotlar
- Turlari: haftalik, oylik, tanlangan davr, raqobatchilar bilan solishtirish, kontent-plan hisoboti, reklama natijasi.
- Formatlar: ekranda, **PDF** va **Excel**.
- **Brend:** agentlik logotipi/ranglari (Sozlamalardan o'zgaradi) va ixtiyoriy ravishda mijoz logotipi; logotip bo'lmasa standart sarlavha.
- Mazmun: asosiy ko'rsatkichlar, grafiklar, eng yaxshi postlar, AI xulosasi va keyingi oy tavsiyalari.
- Avtomatik: jadval bo'yicha yaratiladi va **mijozga Telegram botda yuboriladi** (admin tasdiqlash rejimi ixtiyoriy).

### 4.15. Telegram bot va bildirishnomalar
- **Bot (mijoz kabineti):** 2.5-bandga qarang. Menyu o'zbekcha, tugmalar orqali ishlaydi.
- **Xodimlarga bildirishnomalar** (ichki platforma + Telegram): yangi vazifa, tasdiqlash so'rovi, kontent holati o'zgarishi, nashr muvaffaqiyati/xatosi, kvota ogohlantirishi, token tugashi, anomaliya (o'sish/pasayish), salbiy izoh, hisobot tayyor, provayder almashganligi.
- Foydalanuvchi qaysi turdagi bildirishnomani qayerda (platforma/Telegram) olishini o'zi sozlaydi; admin majburiy turlarni belgilaydi.
- Bildirishnomalar jurnali saqlanadi, takroriy spam oldi olinadi (guruhlash, tanaffus).

### 4.16. Tizim holati (real vaqt)
Admin (va ruxsat berilgan rollar) ko'radi, yangilanish 5–10 soniyada:
- **Provayderlar:** har biri uchun holat (yaxshi/sekin/xato/kvota tugadi), so'nggi muvaffaqiyatli so'rov, o'rtacha kechikish, xatolar foizi, bugungi so'rovlar va qolgan kvota/kredit, joriy ustuvorlik va oxirgi avtomatik almashish sababi.
- **Ulanishlar:** har bir kanal/sahifa uchun token holati, tugash sanasi, oxirgi yig'ish.
- **Navbat:** kutayotgan/bajarilayotgan/xatolik vazifalar, eng uzoq kutayotgani, worker tirikligi (heartbeat).
- **Server:** CPU, RAM, GPU yuklamasi/VRAM, disk, MySQL holati, ish vaqti.
- **R2:** ishlatilgan hajm (9 GB chegara), fayllar soni.
- **Cloudflare Worker:** holat va limit.
- **Tavsiyalar:** tizim o'zi sozlamalarga tuzatish taklif qiladi (masalan, «ScrapeCreators krediti 4 kunda tugaydi, yig'ish chastotasini kamaytiring»).
- Xato yoki kvota chegarasida avtomatik bildirishnoma.

### 4.17. Sozlamalar
- **Umumiy:** tizim nomi, logo, asosiy rang, tema (Dark/Light), til, vaqt zonasi.
- **Foydalanuvchilar, rollar va ruxsatlar** (2-bo'lim).
- **API kalitlar va provayderlar:** Gemini, Groq, OpenRouter, Claude (o'chirilgan), ScrapeCreators, YouTube Data API, Meta app (App ID/Secret), Google OAuth, Telegram (API ID/Hash, bot tokenlar), Cloudflare (R2, Worker). Har biri uchun «Tekshirish» tugmasi.
- **Yig'ish jadvali**, kvota chegaralari, failover qoidalari, ScrapeCreators rejimi va chegaralari.
- **AI Router** jadvali va pullik rejimga o'tish qoidalari.
- **Nashr:** vaqt, R2 qoidalari, qayta urinishlar.
- **Kontent qoidalari** andozalari.
- **Bildirishnoma** sozlamalari.
- Barcha maxfiy qiymatlar interfeysda niqoblangan (`••••1234`), tahrirlash faqat admin.

### 4.18. Audit jurnali
Muhim amallar (kirish, ruxsat o'zgarishi, kalit o'zgarishi, nashr, o'chirish, qoidani chetlab o'tish) kim/qachon/nima/qaysi biznes bilan jurnalga yoziladi; faqat admin ko'radi, o'chirib bo'lmaydi.

---

## 5. XAVFSIZLIK VA MIJOZ AKKAUNTLARINI HIMOYA QILISH

### 5.1. Mijoz akkauntlari xavfsizligi (majburiy qoidalar)
1. Faqat **rasmiy API va OAuth** ishlatiladi. Instagram/YouTube uchun login-parol saqlanmaydi va ishlatilmaydi. Noofitsial scraping o'z akkauntlarda ishlatilmaydi.
2. Barcha tashqi so'rovlar **tezlik cheklovi** (rate limit) va xatoda eksponensial kutish bilan yuboriladi; 429/blok belgisida provayder avtomatik to'xtatiladi va admin'ga xabar beriladi.
3. Telegram akkauntida (Telethon) faqat o'qish; xabar yuborish, qo'shilish, obuna bo'lish funksiyalari kodga kiritilmaydi.
4. Nashr: tasdiqlanmagan kontent chiqmaydi; takroriy nashrdan himoya; har bir biznes/tarmoqda kill switch.
5. Ruxsatlar minimal: har bir ulanishda faqat kerakli scope so'raladi.
6. Tokenlar muddati kuzatiladi, tugashidan oldin yangilanadi yoki ogohlantiriladi.
7. Mijoz hisobotlari va ma'lumotlari boshqa biznesga hech qachon ko'rinmaydi (server tomonda tekshiruv).

### 5.2. Umumiy xavfsizlik
- Parollar Argon2 bilan xeshlanadi; kirishda urinishlar cheklovi (lockout), seans muddati sozlanadi.
- API kalitlar, tokenlar, Telethon sessiyalari **Fernet** bilan shifrlanadi; shifrlash kaliti `.env`da (bazadan alohida).
- Server faqat lokal tarmoq interfeysida tinglaydi; tashqi (global) kirish yo'q. Faqat chiquvchi ulanishlar ruxsat etiladi.
- Telegram bot mijozlarni taklif kodi va foydalanuvchi ID bo'yicha tekshiradi; kod bir marta ishlatiladi va muddati cheklangan.
- Loglarda maxfiy qiymatlar niqoblanadi.
- Lokal tarmoqda ham HTTPS tavsiya etiladi (ichki sertifikat), ixtiyoriy.
- SQL-injection/XSS/CSRF himoyasi Django vositalari bilan; fayl yuklashda tur va hajm tekshiruvi.

---

## 6. TASHQI XIZMATLAR CHEKLOVLARI VA XAVFLAR

### 6.1. Instagram
Professional akkaunt, Facebook Page bilan bog'lash va Meta app kerak. Stories insights qisqa muddat saqlanadi (4.3-band). Raqobatchi uchun chuqur insights mavjud emas, faqat ochiq metrikalar. Meta app ba'zi ruxsatlar uchun «App Review» yoki Business verification talab qilishi mumkin. Boshlang'ich sinovda agentlik app'ining developer rejimi bilan o'z akkauntlarda ishlash mumkin; keng ishlatish uchun tekshiruv jarayoni TZ doirasida alohida bosqich sifatida rejalashtiriladi.

### 6.2. Telegram
Bot API ko'rishlar tarixi va kanal o'sish grafigini bermaydi; shuning uchun statistika Telethon akkaunti (admin) orqali olinadi. Raqobatchi kanallar uchun faqat ochiq ma'lumot. Telegram Ads uchun ochiq kampaniya API'si tasdiqlanmagan (4.12-band).

### 6.3. YouTube
- Data API bepul kunlik kvotasi cheklangan; video yuklash kvotani ko'p sarflaydi, kunlik yuklashlar soni hisoblanadi.
- Yangi Google API loyihalaridan yuklangan videolar Google auditidan o'tguncha cheklangan (yopiq) bo'lishi mumkin. Shuning uchun YouTube avtopost rejasi: (1) 1-bosqichda statistika va OAuth, (2) yuklashni sinash va audit talabini aniqlash, (3) kerak bo'lsa audit arizasi, shu paytgacha video yuklash «yopiq rejim»da bo'ladi va admin xabardor qilinadi.

### 6.4. ScrapeCreators va bepul kreditlar
Bepul rejim boshlang'ich kredit bilan cheklangan. Test rejimida ham kunlik 3–4 yig'ish kredit sarfini tez oshiradi; shuning uchun sarf hisoblagichi, kesh va chegaralar majburiy. Pullik rejim keyin yoqiladi.

### 6.5. Bepul AI limitlari
Bepul tarif limitlari va modellar o'zgarishi mumkin; shuning uchun limitlar tizimga qattiq yozilmaydi, Sozlamalarda o'zgaradi, router esa xatolardan o'rganadi (cooldown).

### 6.6. Texnik xavflar
| Xavf | Chora |
|---|---|
| Bepul AI o'zbek tilida sifatsiz | Til tekshiruvi, qayta yuborish, inson tasdig'i, keyin Claude |
| GTX 1660 Super VRAM (6 GB) cheklovi | Og'ir ishlar bulutda, lokalda faqat yengil bosqichlar |
| Internet uzilishi | Vazifalar navbatda saqlanadi, qayta urinadi; nashr vaqti o'tib ketsa admin'ga xabar |
| Kompyuter o'chib qolishi | Autostart + watchdog, qotgan vazifalarni tiklash |
| API o'zgarishi | Adapter qatlami, bitta joyda tuzatish |

---

## 7. MA'LUMOTLAR BAZASI (asosiy jadvallar)

| Guruh | Jadvallar |
|---|---|
| Foydalanuvchi | `users`, `roles`, `role_permissions`, `user_permission_overrides`, `user_business_access` (user, business, role, all_flag), `audit_logs`, `notifications`, `notification_settings` |
| Biznes | `businesses`, `business_templates`, `brand_profiles` (versiyalar), `business_goals`, `industry_metrics` |
| Ulanish | `social_accounts` (business, platform, external_id, nom, holat, shifrlangan token, token_expires_at, scopes), `telegram_bots`, `telegram_sessions`, `competitors` (business, platform, handle, izoh) |
| Yig'ilgan | `account_metrics_daily`, `account_metrics_intraday`, `posts` (platform, external_id, turi, matn, media_url, published_at), `post_metrics_history`, `stories`, `story_metrics_history`, `comments`, `competitor_metrics`, `competitor_posts` |
| Kontent | `content_plans`, `content_items` (status, mas'ul, rejalashtirilgan vaqt, tarmoqlar), `content_assets`, `publish_attempts`, `r2_objects` (kalit, hajm, holat), `content_rule_sets`, `rule_check_results` |
| AI | `scripts`, `script_analyses`, `hooks`, `ai_generations`, `ai_providers`, `ai_keys`, `ai_routes`, `ai_usage_log`, `ai_cache`, `comment_reply_suggestions`, `post_insights` ("nega ishladi") |
| Media | `media_files`, `media_analyses` |
| Provayderlar | `data_providers`, `provider_keys`, `provider_usage_log`, `provider_failover_events` |
| Reklama | `ad_budgets`, `ad_recommendations`, `ad_campaigns`, `ad_results`, `sales_forecasts`, `leads_sales` (qo'lda kiritilgan) |
| Havolalar | `short_links`, `link_clicks`, `worker_status` |
| Hisobot | `reports`, `report_schedules`, `client_bot_users`, `client_invites` |
| Tizim | `jobs`, `job_logs`, `system_settings`, `health_snapshots` |

Tamoyillar: barcha biznesga tegishli jadvallarda `business_id` (indekslangan); metrikalar tarixiy (hech qachon ustiga yozilmaydi, vaqt bilan qo'shiladi); maxfiy maydonlar shifrlangan; 3 oydan eski avtomatik import yo'q, lekin bir marta yig'ilgan ma'lumot saqlanadi.

---

## 8. FOYDALANUVCHI INTERFEYSI VA DIZAYN

- **Uslub:** zamonaviy, toza, keng bo'shliqli, yumaloq burchaklar, yengil animatsiya; kartalar, aniq ierarxiya.
- **Ranglar:** asosiy **qizil**, **ko'k** va **oq**; Dark (qora/to'q kulrang fon) va Light rejimlar, foydalanuvchi tanlovi saqlanadi. Brend rangi va logotip Sozlamalardan o'zgaradi (hozircha standart).
- **Adaptivlik:** kompyuter asosiy, planshet/telefon brauzerda ham qulay.
- **Navigatsiya:** chap menyu (ruxsatga qarab), yuqorida biznes tanlagich, qidiruv, bildirishnomalar, profil.
- **Asosiy sahifalar:** Boshqaruv paneli · Bizneslar · Ulanishlar · Tahlil · Raqobatchilar · Kontent kalendar · AI studiya (Plan, Ssenariy, Hook bazasi, Izohlar) · Media tahlil · Reklama · Hisobotlar · Havolalar · Tizim holati · Sozlamalar · Foydalanuvchilar.
- Grafiklar interaktiv, jadvallar saralanadigan va eksport qilinadigan; yuklanish holatlari (skeleton), bo'sh holat matnlari va aniq xato xabarlari o'zbek tilida.
- Uzoq vazifalar (tarixiy import, AI, video tahlil) uchun progress ko'rsatkichi.

---

## 9. NOFUNKSIONAL TALABLAR

- **Unumdorlik:** oddiy sahifa < 2 soniyada ochiladi; 10–20 bir vaqtdagi foydalanuvchi.
- **Ishonchlilik:** 24/7 ishlash, autostart, watchdog, qayta urinish; muhim xatolar jurnali (`logs/`) aylantirib saqlanadi.
- **Kengaytiriluvchanlik:** yangi tarmoq/provayder/AI modeli adapter qo'shish orqali; yangi biznes sonining oshishi arxitekturani o'zgartirmaydi.
- **Qulaylik:** barcha matn o'zbekcha, xato xabarlari tushunarli.
- **Hujjatlashtirish:** ulash qo'llanmalari (Meta app, Google Cloud, Telegram bot/Telethon, R2, Cloudflare Worker, Gemini/Groq/OpenRouter kalitlari) `docs/` papkasida qadamma-qadam.
- **Zaxira nusxa:** hozircha qamrovdan tashqari (kerak bo'lsa, alohida modul).

---

## 10. BOSQICHLAR VA YETKAZIB BERILADIGAN NATIJALAR

### 1-bosqich: Asos va ma'lumot yig'ish
`run.bat`/`stop.bat`/autostart; foydalanuvchilar, rollar, ruxsat matritsasi, biznesga biriktirish; bizneslar va biznes andozalari; ulanishlar (Telegram kanal+bot, Telethon, YouTube OAuth); provayder qatlami (YouTube Data API + ScrapeCreators, failover); collector va jadval; tarixiy saqlash; asosiy dashboard va tahlil; Sozlamalar; Tizim holati (asosiy); bildirishnomalar (asosiy); Dark/Light dizayn.

### 2-bosqich: Instagram, raqobatchilar, kontent va nashr
Instagram Graph API ulanishi va insights; stories tarixi; raqobatchilar moduli va solishtirish; kontent kalendar, tasdiqlash oqimi, vazifalar; kontent qoidalari; avtomatik nashr (Telegram, Instagram, YouTube) va Cloudflare R2 (9 GB nazorati, avtomatik o'chirish); mijoz Telegram boti (kabinet, hisobotlar).

### 3-bosqich: AI
AI Router (Gemini, Groq, OpenRouter, Claude o'chirilgan holda tayyor); brend xotirasi; "Nega ishladi" tahlili; oylik kontent-plan; ssenariy generatori va tahlili; Hook bazasi; izohlarga javob tavsiyalari; AI hisobotlari.

### 4-bosqich: Media tahlil, reklama va hisobotlar
Gibrid media tahlil; reklama tavsiyalari va sotuv prognozi, Telegram Ads matn/tavsiya, Meta target tavsiyalari; Cloudflare Worker havolalari va klik hisobi; PDF/Excel logotipli hisobotlar va mijozga avtomatik yuborish; Tizim holati to'liq (tavsiyalar bilan); yakuniy sinov va hujjatlar.

---

## 11. DASTLABKI TAYYORGARLIK RO'YXATI (siz tomondan)

| № | Nima | Holat |
|---|---|---|
| 1 | Meta Developer app (Instagram Graph API, ruxsatlar) | Mavjud |
| 2 | Har bir biznes: Instagram Professional + Facebook Page bog'lanishi | Tekshirish kerak |
| 3 | Google Cloud Console loyihasi: YouTube Data API v3, Analytics API, OAuth | Yaratiladi |
| 4 | Telegram: agentlik boti (mijoz kabineti), kanal botlari, Telethon uchun API ID/Hash va akkaunt | Akkaunt mavjud |
| 5 | Cloudflare: R2 bucket va API token; Worker uchun akkaunt | Yaratiladi |
| 6 | Gemini (AI Studio), Groq, OpenRouter kalitlari | Yaratiladi |
| 7 | ScrapeCreators API kaliti (bepul kreditlar) | Yaratiladi |
| 8 | MySQL 8 o'rnatish (yoki portable) | Yaratiladi |
| 9 | `ads.telegram.org` kabineti | Mavjud |
| 10 | Server: Windows, Python 3.12, FFmpeg, 24/7 elektr/internet | Tayyorlanadi |

---

## 12. TAXMINLAR VA OCHIQ MASALALAR

1. Bepul AI va ScrapeCreators limitlari aniq kalitlar olingach tekshiriladi va Sozlamalarga kiritiladi.
2. Telegram Ads uchun kampaniya API'si bor-yo'qligi 4-bosqichdan oldin aniqlanadi; hozircha tavsiya + qo'lda kiritish rejimi.
3. Meta Marketing API orqali kampaniyani avtomatik yaratish ixtiyoriy kengaytma; ad account va to'lov usuli tayyor bo'lgach qaror qilinadi.
4. YouTube audit talabi 2-bosqichda sinab ko'riladi (6.3-band).
5. Meta app'ning keng ishlatish uchun tekshiruvi (App Review) kerak bo'lsa, 2-bosqichda alohida vazifa.
6. Sotuv prognozi dastlab taxminiy ko'rsatkichlar bilan ishlaydi; aniqligi real kampaniya natijalari kiritilgach oshadi.
7. CRM integratsiyasi, zaxira nusxa, KPI paneli va 5-bosqich (yangi tarmoqlar) keyinga qoldirilgan.

---

## 13. QABUL MEZONLARI

- `run.bat` toza Windows kompyuterida (Python va MySQL bilan) tizimni ishga tushiradi; qayta yoqilganda avtomatik tiklanadi.
- Admin ruxsatlarni rol bo'yicha qo'lda sozlay oladi; foydalanuvchi faqat ruxsat berilgan biznes va bo'limlarni ko'radi (server tomonda tekshiriladi).
- Har bir biznesda Telegram/Instagram/YouTube ulanishlarini (1–5+) qo'shish, tahrirlash, o'chirish mumkin.
- Yig'ish kuniga 3–4 marta ishlaydi, metrikalar va stories tarixi bazada saqlanadi.
- YouTube Data API ⇄ ScrapeCreators almashinuvi kvota/kredit tugaganda avtomatik ishlaydi va "Tizim holati"da ko'rinadi.
- Rejalashtirilgan post tasdiqdan keyin avtomatik chiqadi, R2 fayli o'chiriladi, R2 hajmi 9 GB'dan oshmaydi.
- AI Router bepul provayderlar orasida avtomatik almashadi; Claude API Sozlamalardan yoqilmaguncha ishlatilmaydi.
- Brend xotirasi yaratiladi, versiyalanadi va barcha AI natijalarida ishlatiladi.
- Oylik plan, ssenariy, ssenariy tahlili, "nega ishladi" tahlili, hook bazasi va izoh javob tavsiyalari ishlaydi.
- Media tahlil gibrid rejimda qisqa videoda taxminan 1–2 daqiqada natija beradi.
- Reklama tavsiyasi byudjet va maqsadga qarab post, vaqt va uch stsenariyli taxminiy prognoz beradi.
- Cloudflare Worker havolalari tizimdan yaratiladi, boshqariladi, kliklar ko'rinadi.
- Mijoz faqat Telegram bot orqali o'z biznes hisobotini oladi, veb-platformaga kira olmaydi.
- PDF/Excel hisobotlar logotip bilan yaratiladi.
- Bildirishnomalar va Tizim holati real vaqtda ishlaydi.
