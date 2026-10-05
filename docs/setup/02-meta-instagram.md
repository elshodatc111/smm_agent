# 2. Instagram ulash (Meta, «Instagram Login» yo'li)

**Xavfsizlik qoidasi:** tizim hech qachon mijozning Instagram login/parolini so'ramaydi va ishlatmaydi. Faqat **rasmiy OAuth** orqali, mijoz o'zi ruxsat beradi. Ruxsatni mijoz istalgan vaqtda Instagram sozlamalaridan bekor qila oladi. Parol bilan «avtomatik kirish» usullari akkauntning bloklanishiga olib keladi — shuning uchun ular yo'q.

**Talablar:** mijozning Instagram akkaunti **Professional** (Business yoki Creator) bo'lishi kerak. Facebook sahifasi **shart emas** («Instagram Login» yo'li shuni beradi).

## A. Meta Developer ilovasi yaratish (agentlik uchun bir marta)

1. developers.facebook.com ga o'zingizning Facebook akkauntingiz bilan kiring → **Get Started** (developer sifatida ro'yxatdan o'ting).
2. **My Apps → Create App**. Use case sifatida **Other** (yoki «Business») → App type: **Business**. Nom: masalan `SMM Platforma`.
3. Ilova panelida **Add product → Instagram** (yoki «Instagram API with Instagram Login») ni qo'shing.
4. **App settings → Basic** da **App ID** va **App Secret** ni ko'rasiz. Ularni tizimda **Sozlamalar → API kalitlar** ga kiriting (Meta App ID, Meta App Secret).
5. Instagram mahsuloti sozlamalarida **Business login settings** → **Valid OAuth Redirect URIs** maydoniga quyidagini qo'shing:

   `https://<WORKER_MANZILI>/oauth/instagram/callback`

   Masalan: `https://smm-links.mening-akkauntim.workers.dev/oauth/instagram/callback`. Worker'ni 5-bo'limda sozlaysiz — manzilni shundan olasiz. **Instagram uchun https shart**, shuning uchun bu yerda Cloudflare Worker kerak.
6. Ilova ichida talab qilinadigan ruxsatlar (scopes), tizim so'raydi:
   `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`, `instagram_business_manage_insights`.

## B. Development rejimida ulash (mijoz akkauntisiz sinash)

Ilova **Development** rejimida turganda faqat ilovada **roli bor** odamlar ulana oladi:

1. **App roles → Roles → Add People** — o'zingizni (Admin/Developer) va sinovchini (Tester) qo'shing.
2. Instagram akkauntlar uchun: **Instagram → API setup with Instagram login → Add Instagram testers**/«Instagram Testers» ga akkauntni qo'shing; akkaunt egasi Instagram ilovasida: *Settings → Apps and websites → Tester invitations* orqali qabul qiladi.
3. Tizimda **Ulanishlar → Yangi ulanish → Instagram ulash** ni bosing → Instagram ruxsat oynasi → «Allow». Ulanish yaratiladi va 90 kunlik tarixiy import boshlanadi.

Bu rejimda o'zingizning va sinovchilarning akkauntlarini to'liq ulash, statistika olish va nashr qilish mumkin.

## C. Haqiqiy mijozlar uchun (Live rejim)

Ilovada roli yo'q **begona** mijoz akkauntini ulash uchun Meta **App Review** va, odatda, **Business Verification** talab qiladi:

1. **App settings → Basic**: Privacy Policy URL, App icon, kategoriya, Data deletion instruction/URL to'ldiring (oddiy sahifa yetarli).
2. **Business Verification** (Business settings → Security Center): kompaniya hujjatlari. Bir necha kundan haftagacha.
3. **App Review → Permissions and Features**: yuqoridagi 4 ta ruxsat uchun **Request advanced access**. Har biri uchun *screencast video* (tizimning ulanish → statistika → nashr ishlashini ko'rsatadigan qisqa yozuv) va nima uchun kerakligi izohi yuboriladi.
4. Tasdiqdan keyin ilovani **Live** qiling.

> Review muddati va talablar Meta tomonidan o'zgarib turadi; ekrandagi so'nggi ko'rsatmalarga amal qiling. Review kutilayotgan vaqtda ham **o'zingizning/sinovchi akkauntlar** bilan butun tizimni ishlatib ko'rishingiz mumkin.

## D. Token haqida (siz hech narsa qilmaysiz)

- Ulanishdan so'ng tizim **uzoq muddatli token** (60 kun) oladi va bazada shifrlab saqlaydi.
- Worker har kuni tekshiradi va tokenni muddati tugashidan oldin, kamida 24 soatlik bo'lgach, **avtomatik yangilaydi**.
- Yangilash muvaffaqiyatsiz bo'lsa «Ulanishlar» sahifasida *Token tugayapti* belgisi va bildirishnoma chiqadi → **Qayta ulash (OAuth)** tugmasini bosing.

## E. Nashr qanday ishlaydi

- Rasm: Instagram **ommaviy URL** talab qiladi. Tizim rasmni Cloudflare Worker orqali vaqtincha ochiq qiladi (bepul), nashrdan so'ng o'chiradi.
- Video/Reels: Instagram'ning *resumable upload* usuli bilan to'g'ridan-to'g'ri yuklanadi — R2 yoki ommaviy havola **shart emas**, shuning uchun rejalashtirilgan Reels/Stories uchun hajm muammosi yo'q.
- Nashr 3 bosqichli: konteyner yaratish → tayyor bo'lishini kutish → `media_publish`. Xato bo'lsa takror nashr bo'lmasligi uchun avval holat tekshiriladi.

## Muammolar

| Xabar | Sabab |
|---|---|
| «Instagram akkaunt Professional bo'lishi kerak» | Instagram → Settings → Account type → Switch to professional |
| Redirect URI mos kelmadi | 5-qadamdagi URI Meta'da aynan shunday (https, oxirida `/oauth/instagram/callback`) kiritilganini tekshiring |
| Ruxsat oynasida «bu ilova mavjud emas» | Akkaunt tester sifatida qo'shilmagan yoki taklif qabul qilinmagan |
