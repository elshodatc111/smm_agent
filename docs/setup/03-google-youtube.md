# 3. YouTube ulash (Google Cloud)

## Muhim: «Testing» holatidagi token muammosi va yechim

Google OAuth ilovasi **Testing** holatida bo'lsa, `refresh token` **7 kundan keyin o'ladi** — kanalni har hafta qayta ulashga to'g'ri keladi. Buning yagona to'g'ri yechimi: OAuth ilovasini **Production** holatiga o'tkazish. Shunda refresh token muddatsiz yashaydi va tizim access tokenni o'zi yangilaydi (qo'lda hech narsa qilmaysiz).

- Production'ga o'tish uchun Google ilovani «tasdiqlash» (verification) shartini qo'yishi mumkin. **O'z kanallaringiz uchun** (siz yoki mijoz o'z akkauntini bergan holda) ilova «unverified» holatda ham ishlaydi: ruxsat oynasida «Google hasn't verified this app» ogohlantirishi chiqadi, **Advanced → Go to … (unsafe)** orqali davom etiladi. Foydalanuvchilar soni cheklovi (100 tagacha) bor — agentlik uchun yetarli.
- Muhim cheklov: *tasdiqlanmagan* loyihalardan `videos.insert` orqali yuklangan videolar Google siyosatiga ko'ra **private (yopiq)** qilib qo'yilishi mumkin. Agar shunday bo'lsa, ilova uchun YouTube **API audit** so'rang (Google Cloud → YouTube API Services → Audit and Quota Extension form). Statistika va izohlarni o'qish bunga bog'liq emas.
- Kvota: standart kunlik limit **10 000** birlik; bitta video yuklash **~1 600** birlik → kuniga **~6 ta video**. Tizim buni hisoblab boradi va oshib ketishdan oldin ogohlantiradi/yuklashni ertaga qoldiradi. Ko'proq kerak bo'lsa kvota oshirish so'rovini yuboring.

## A. Loyiha va API'larni yoqish

1. console.cloud.google.com ga kiring → yuqoridan **Select a project → New Project** → nom: `SMM Platforma`.
2. **APIs & Services → Library** da quyidagilarni **Enable** qiling:
   - *YouTube Data API v3*
   - *YouTube Analytics API*
3. **APIs & Services → Credentials → Create credentials → API key** — bu **YouTube API kaliti** (ochiq ma'lumotlar uchun). Tizimda *Sozlamalar → API kalitlar → YouTube Data API kaliti* ga kiriting. Xavfsizlik uchun kalitga «Restrict key → YouTube Data API v3» cheklovini qo'ying.

## B. OAuth rozilik ekrani (Consent screen)

1. **APIs & Services → OAuth consent screen** (yangi interfeysda *Google Auth Platform → Branding/Audience*).
2. User type: **External**. App name, support email, developer email to'ldiring.
3. **Scopes** (yoki Data Access) ga qo'shing:
   - `.../auth/youtube.readonly`
   - `.../auth/youtube.upload`
   - `.../auth/yt-analytics.readonly`
   - `.../auth/youtube.force-ssl` (izohlarga javob uchun)
4. **Audience / Publishing status → PUBLISH APP (Production)**. Test foydalanuvchilar ro'yxati kerak bo'lmaydi.

## C. OAuth Client ID

1. **Credentials → Create credentials → OAuth client ID** → Application type: **Web application**.
2. **Authorised redirect URIs** ga quyidagini qo'shing:

   `https://<WORKER_MANZILI>/oauth/youtube/callback`

   (Worker'ni 5-bo'limda sozlaysiz.)
3. Yaratilgach **Client ID** va **Client secret** ni tizimdagi *Sozlamalar → API kalitlar* ga kiriting.

> **Ehtiyot varianti.** Agar Google `workers.dev` manzilini redirect URI sifatida qabul qilmasa (xabar: *"must end with a public top-level domain"*), quyidagicha qiling: Google'da redirect URI sifatida `http://localhost:8000/oauth/youtube/done/` ni qo'shing, tizimda *Sozlamalar → API kalitlar → OAuth callback bazasi* ga `http://localhost:8000` yozing va YouTube'ni ulashni **server kompyuterning o'zida** `http://localhost:8000` orqali bajaring. Ulangandan keyin token avtomatik yangilanadi, qayta ulash kerak emas. Shuningdek o'zingizning domeningiz bo'lsa (Cloudflare'ga ulangan), Worker'ga shu domen orqali `https://...` manzil bering.

## D. Kanalni ulash

1. Tizimda **Ulanishlar → Yangi ulanish → YouTube ulash**.
2. Google oynasida kanal egasi akkauntini tanlang → ruxsatlarni bering. «Google hasn't verified this app» chiqsa: **Advanced → Go to (unsafe)**.
3. Brand-akkaunt (kanal alohida «Brand account» bo'lsa) — ruxsat oynasida aynan o'sha kanalni tanlang.
4. Ulanish yaratiladi, tarixiy import boshlanadi.

## E. Token qanday yangilanadi

Tizim har bir so'rovdan oldin access tokenni tekshiradi, muddati yaqin bo'lsa `refresh token` bilan yangisini oladi. Refresh token Production holatida o'lmaydi. Foydalanuvchi Google akkauntida ilovaga ruxsatni bekor qilsa (`invalid_grant`) — ulanish «Xato» holatiga o'tadi, bildirishnoma keladi va «Qayta ulash» tugmasi chiqadi.

## Muammolar

| Xabar | Yechim |
|---|---|
| `redirect_uri_mismatch` | Google'dagi URI va tizim yuborayotgan URI aynan bir xil emas (http/https, oxiridagi `/`). |
| Refresh token berilmadi | Ilovaga ruxsatni https://myaccount.google.com/permissions dan olib tashlab, qayta ulang. |
| 403 quotaExceeded | Kunlik kvota tugagan; Tichiy okean vaqti bilan yarim tunda (Toshkent ~13:00) yangilanadi. Tizim o'zi zaxira provayderga o'tadi. |
