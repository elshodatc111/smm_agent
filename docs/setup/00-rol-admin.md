# Admin uchun yo'riqnoma

Admin — tizimning egasi. U hamma narsani ko'radi va sozlaydi. Bu yo'riqnoma birinchi kundan boshlab kundalik ishgacha tartib bilan yozilgan.

## 1. Birinchi sozlash (bir marta)

1. **Bizneslar** → «Yangi biznes». Eng ko'pi bilan 10 ta biznes qo'shiladi.
2. **Ulanishlar** → Telegram kanal, Instagram, YouTube ni ulang. Faqat rasmiy ulash (OAuth) ishlatiladi: mijozning login va parolini hech qachon so'ramang.
3. **Sozlamalar → Kalitlar** → AI kalitlari (Groq/Gemini va h.k.), Cloudflare R2 kalitlari, Mijoz boti. Kalitlarni faqat shu formalarga kiriting; ular shifrlanadi va keyin faqat niqoblangan ko'rinishda chiqadi.
4. **Foydalanuvchilar** → xodimlarni rol bilan qo'shing (pastga qarang).

![Boshqaruv paneli](/static/guide/dashboard.png)

## 2. Xodimlarga rol berish

| Rol | Kimga | Nima qila oladi |
|---|---|---|
| Menejer | Loyiha rahbari | Ko'rish, yaratish, tahrirlash, o'chirish, nashr qilish, hisobot |
| SMM mutaxassis | Kontent yurituvchi | Post yaratish va tahrirlash, AI, tahlilni ko'rish. Hozir-nashr tugmasi yo'q |
| Kontent-maker (dizayner) | Rasm/video tayyorlovchi | Kalendar va media bilan ishlash, fayl yuklash |
| Targetolog | Reklama | Reklama tavsiyalari, tahlil, havolalar |
| Analitik | Tahlilchi | Tahlil, hisobotlar |

Har bir xodimga faqat o'z bizneslarini bering (Foydalanuvchilar → kirish huquqi).

## 3. Xodimlar nazorati — Faoliyat jurnali

«Tizim → Faoliyat jurnali» da har bir xodim nima qilgani ko'rinadi: kim, qachon, qaysi post, qanday amal. Xodim, sana va amal turi bo'yicha saralash mumkin. Yozuvlarni o'chirib yoki o'zgartirib bo'lmaydi.

![Faoliyat jurnali](/static/guide/faoliyat.png)

Har kuni ertalab soat 8 dan keyin sizga **kunlik xulosa** keladi: «kecha kim nima qildi». U Telegram'ga (profilingizga Telegram ID kiritilgan bo'lsa) va ilova ichidagi bildirishnomalarga tushadi.

Har bir postning ichida ham «Tarix — kim nima qildi» bo'limi bor: yaratildi, tahrirlandi, media qo'shildi, nashr urinishlari.

## 4. Cloudflare ombori

Katta fayllar va barcha media Cloudflare R2 ga joylanadi. «Cloudflare» menyusida har bir faylning holati (Yuklanmoqda, Yuklangan, Xato) ko'rinadi. Fayllar **faqat qo'lda** o'chiriladi — avtomatik o'chirish yo'q.

![Cloudflare menyusi](/static/guide/cloud.png)

## 5. Har hafta tekshiring

1. Tizim holati — hamma xizmat yashilmi.
2. Ulanishlar — tokenlar muddati tugamayaptimi.
3. Faoliyat jurnali — g'alati harakatlar (ko'p o'chirishlar, begona kirishlar).
4. Savat va Cloudflare — keraksiz fayllarni tozalash.
5. Zaxira nusxa (09-zaxira bo'limi).

## 6. Xavfsizlik qoidalari

- Mijoz akkauntining login/parolini so'ramang va saqlamang.
- Kalitlarni chatga yoki xatga yozmang — faqat Sozlamalar formalariga.
- Xodim ketsa — darhol Foydalanuvchilar'dan o'chirib qo'ying.
