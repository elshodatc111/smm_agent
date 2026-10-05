# 7. ScrapeCreators (raqobatchi va ochiq ma'lumot, zaxira provayder)

**Nima uchun kerak:** raqobatchilarning ochiq profil/post ma'lumotlarini olish (ularning akkauntiga ulanish mumkin emas), shuningdek YouTube kvotasi tugaganda zaxira.

**Tamoyil:** tizim **kredit sarfini qattiq nazorat qiladi** — byudjet aniq bo'lmaganda ham hech narsa «oqib ketmaydi».

## Olish

1. scrapecreators.com da ro'yxatdan o'ting (yangi akkauntga sinov krediti beriladi — miqdori o'zgarib turadi).
2. Dashboard'dan **API key** ni oling.
3. Tizimda *Sozlamalar → API kalitlar → ScrapeCreators kaliti* ga kiriting, «ScrapeCreators» tugmasi bilan tekshiring.

## Himoya sozlamalari (*Sozlamalar → Provayderlar*)

| Sozlama | Standart | Ma'nosi |
|---|---|---|
| Rejim | `free` | Bepul kredit rejimi: kunlik/oylik limitlar qat'iy |
| Kunlik limit | 50 | Bir kunda sarflanadigan maksimal kredit |
| Oylik limit | 500 | Oy bo'yicha maksimum |
| Bir yig'ish chegarasi | 10 | Bitta ish uchun maksimal kredit |
| Ogohlantirish chegarasi | 20 | Qoldiq shundan past tushsa provayder avtomatik o'chadi + bildirishnoma |
| Kesh | 6 soat | Bir xil so'rov qayta pul turmaydi |

Raqobatchilar: kuniga 1–3 ta yengil tekshiruv (profil), haftada 1 ta to'liq (postlar bilan) — standart. «Tizim holati» da qoldiq kredit va «necha kunga yetadi» prognozi ko'rinadi.

**Pullik rejaga o'tganda:** rejim `paid` va limitlarni oshiring. Hozircha byudjet yo'q bo'lsa — standart qiymatlar bilan qoldiring, tizim bepul kredit tugagach ScrapeCreators'ni o'zi o'chiradi va YouTube/Telegram uchun boshqa manbalarga o'tadi.

## Provayderlar tartibi (failover)

| Tarmoq | Ustuvorlik |
|---|---|
| YouTube | Data API → ScrapeCreators |
| Telegram | t.me ommaviy sahifa → ScrapeCreators |
| Instagram | ScrapeCreators (raqobatchilar uchun) |

O'z akkauntlaringiz statistikasi **doim rasmiy API** dan olinadi. Almashishlar «Tizim holati» da yoziladi (kim → kim, sababi).

> Tekshirish kerak: ScrapeCreators endpointlari va javob formatlari ularning hujjatlariga muvofiq turishini birinchi ulashda «Tekshirish» tugmasi va bitta raqobatchi bilan sinab ko'ring; formatlari o'zgargan bo'lsa Tizim holati sahifasida xato ko'rinadi.
