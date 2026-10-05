# 4. Telegram: bot, kanal, Telethon akkaunti, mijoz boti

Telegram uchun uchta alohida narsa bor. Ularni aralashtirmang:

| Nima | Nima uchun | Xavf |
|---|---|---|
| **Kanal boti** | Kanalga post yuborish, obunachi sonini olish | Past (rasmiy Bot API) |
| **Telethon akkaunti** (ixtiyoriy) | Kanalning chuqur statistikasi, faqat O'QISH | O'rta — shuning uchun alohida SIM + himoyalar |
| **Mijoz kabineti boti** | Mijoz hisobotni/natijani Telegramda ko'radi | Past |

> Eslatma: Telegram kanalini «bot tokeni» bilan ulash xavfsiz va oson. Instagram uchun bunday «token/login» usuli **yo'q** — u faqat rasmiy OAuth bilan ulanadi (2-bo'lim).

## A. Kanal botini yaratish

1. Telegramda `@BotFather` ni oching → `/newbot` → nom va `...bot` bilan tugaydigan username bering.
2. BotFather bergan **token** ni saqlang (`123456:ABC...`). Uni hech kimga bermang.
3. **Botni kanalga administrator qiling:** kanal → *Administrators → Add Administrator* → botni tanlang → ruxsatlar: **Post messages**, **Edit messages**, **Delete messages** (hammasi yoqilgan).
4. Tizimda **Ulanishlar → Yangi ulanish → Telegram kanal**: nomi, kanal (`@kanal_username` yoki yopiq kanal uchun `-100…` ID), yangi bot tokeni → «Ulash va tekshirish».
   Tizim botning admin ekanini va ruxsatlarini tekshiradi; yetishmasa nima kerakligini yozadi.
5. Bitta botni bir nechta kanalga ulash mumkin — keyingi kanal uchun «Bot (mavjud)» ro'yxatidan tanlang.

Yopiq kanal ID sini bilish: kanaldan biror postni `@userinfobot`/`@RawDataBot` ga forward qiling yoki kanal havolasidagi raqamga `-100` qo'shing.

## B. Telethon akkaunti (ixtiyoriy, chuqur statistika uchun)

Bot API obunachi sonini beradi, lekin postlarning ko'rishlari, obunachilar dinamikasi kabi chuqur statistikani faqat kanal **admini** akkaunti ko'ra oladi. Buning uchun Telethon (foydalanuvchi akkaunti) ishlatiladi.

### Ban'dan himoya qoidalari (tizim buni avtomatik bajaradi)

- **Alohida SIM/raqam** ishlating — asosiy raqamingizni emas. Bu akkaunt ommaviy yoki shaxsiy yozishmalar uchun ishlatilmaydi.
- Akkaunt **faqat o'qiydi**: kodda ruxsat etilgan metodlar ro'yxati (whitelist) bor — xabar yuborish, a'zo qo'shish, kanalga kirish kabi har qanday yozuvchi amal **dasturiy ravishda to'sib qo'yilgan**.
- Har so'rov orasida tasodifiy kutish (3–9 soniya), kunlik so'rov limiti (standart 400), faol soatlar (08:00–23:00).
- `FloodWait` xatosi kelsa tizim aynan shuncha vaqt to'xtaydi; ketma-ket 3 xatodan so'ng sessiya **o'zini o'chirib** qo'yadi va sizga bildirishnoma yuboradi.
- Akkauntni mumkin qadar «tabiiy» saqlang: unga profil rasmi, ism qo'ying, Telegram ilovasida vaqti-vaqti bilan o'zingiz kirib turing; yangi SIM'ni ro'yxatdan o'tgach 1–2 kun kutib ulang.
- Hech qanday kafolat yo'q: Telegram qoidalari o'zgarishi mumkin. Shu sababli kritik ish (nashr) faqat rasmiy Bot API orqali; Telethon yo'qolsa ham tizim ishlayveradi (faqat chuqur statistika bo'lmaydi).

### Sozlash

1. my.telegram.org ga **ajratilgan raqam** bilan kiring → **API development tools** → ilova yarating (nomi ixtiyoriy) → **api_id** va **api_hash** ni oling.
2. Tizimda *Sozlamalar → API kalitlar* da **Telegram API ID** va **API Hash** ni kiriting.
3. Ajratilgan raqamni kanalga **administrator** qiling (faqat «View statistics» yetarli; boshqa ruxsatlarni bermang).
4. **Ulanishlar → Telethon sessiyasi qo'shish**: telefon raqam → Telegramga kelgan kod → (2 bosqichli parol bo'lsa) parol. Sessiya shifrlangan holda bazada saqlanadi.
5. Kanal ulashda «Telethon sessiyasi» maydonidan shu sessiyani tanlang.

Sessiya matni (`StringSession`) akkauntga to'liq kirish beradi: bazani va `.env` ni himoyalang, zaxira nusxalarni begonaga bermang.

## C. Mijoz kabineti boti

Mijozlar o'z natijalarini/hisobotlarini Telegramda ko'radigan alohida bot.

1. `@BotFather` da yana bitta bot yarating (masalan `AgentlikHisobot_bot`), tokenni oling.
2. *Sozlamalar → API kalitlar → Mijoz kabineti boti tokeni* ga kiriting.
3. **Foydalanuvchilar → Mijoz bot taklifnomalari**: bizneslarni tanlang → «Kod yaratish». Kod faqat bir marta ko'rinadi.
4. Mijoz botga `/start KOD` yuboradi → ulanadi. Endi u faqat o'z bizneslari bo'yicha: umumiy ko'rinish, haftalik/oylik hisobot, kontentni tasdiqlash yoki o'zgartirish so'rash imkoniyatiga ega bo'ladi.
5. Kod muddati (standart 72 soat) tugagach yaroqsiz. Mijozni o'chirish: shu sahifada «O'chirish».

Bot ishlashi uchun worker (run.bat) yoqilgan bo'lishi kerak — bot shu jarayon ichida ishlaydi (webhook/domen kerak emas).

## D. Xodimlar bildirishnomalari

Foydalanuvchi profilida **Telegram ID** kiritilsa (`@userinfobot` dan oling), muhim bildirishnomalar (nashr xatosi, token tugashi, kvota) unga mijoz-kabinet boti orqali ham keladi. Avval u botga `/start` bosgan bo'lishi kerak.
