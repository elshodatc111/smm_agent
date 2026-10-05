# 13. Yangi imkoniyatlar (qisqa qo'llanma)

- **Karusel tartibi** — post sahifasida/formada ◀ ▶ tugmalari bilan fayl tartibini o'zgartiring.
- **Qoralama avtosaqlash** — forma yarim to'ldirilgan holda yopilsa, qayta ochganda tiklanadi (7 kun).
- **Kalendarda sudrash** — postni boshqa kunga sudrab o'tkazing (vaqt saqlanadi; nashr qilingan/o'tgan kunga bo'lmaydi).
- **Shablonlar** — postdagi «Shablonga saqlash», yangi post formasida shablon tanlash. O'zgaruvchilar: `{sana}`, `{kun}`, `{biznes}`.
- **Qidiruv** — tepada: post, fayl, g'oya, ssenariy bo'yicha.
- **Aniq ko'rinish** — formadagi «Aniq ko'rinish» tugmasi platformaga yuboriladigan aynan o'sha rasmni ko'rsatadi.
- **Dizayner ish oqimi** — postga vazifa, muddat, izoh; holatlar: bajarilmoqda → tayyor → qayta ko'rish → qabul. «Vazifalarim» sahifasi.
- **Natija xulosasi** — nashrdan 24 soat va 7 kun keyin post kartasida avtomatik xulosa chiqadi.
- **Stories** — chuqur ma'lumot (ko'rish, profilga o'tish, obuna) 20 soatdan keyin yig'iladi.
- **Mijoz boti** — har nashr haqida mijozga avtomatik xabar: qaysi post/story, qaysi platforma, qachon. Bot sozlamalarida «Nashr xabarlari» bo'limi orqali yoqiladi/o'chiriladi.
- **Mijozga chiroyli hisobot** — Hisobotlar → «Ko'rish» (chop etish/PDF) va «Havola» (muddatli ochiq havola; `Sozlamalar → Umumiy → Ochiq manzil` kiritilgan bo'lsin).
- **Kunlik statistika** — lidlar, obunachilar, ko'rishlar kun-kunlab saqlanadi, grafik va CSV.
- **G'oyalar banki** — raqobatchi va o'z natijalaringiz asosida har kuni kamida 1 yangi g'oya, har biriga rejissyor ssenariysi; «Postga aylantirish».
- **Aqlli ogohlantirishlar** — 22 ta detektor, sozlash: Ogohlantirishlar sahifasi.
- **AI rejimi** — Sozlamalar → AI router → «AI rejimi»: `free_first` (bepul avval), `openai_first`, `openai_only` (faqat OpenAI; pullik Claude baribir o'chiq). OpenAI-only javob sifatini va barqarorligini oshiradi (ayniqsa o'zbekcha uzun matn/reja/ssenariy), lekin har so'rov pullik — oylik byudjet Sozlamalarda ko'rinadi.
- **Telefon ilovasi (PWA)** — `/ilova/` sahifasida yo'riqnoma. Telefonda o'rnatish uchun HTTPS kerak (Cloudflare Tunnel tavsiya etiladi); kompyuterning o'zida `localhost` da ishlaydi.
