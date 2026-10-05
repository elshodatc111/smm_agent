# 5. Cloudflare Worker (bepul): havolalar, OAuth callback, vaqtinchalik fayl

Bitta bepul Cloudflare Worker uchta ishni bajaradi:

1. **OAuth callback** — Instagram/Google `https` manzil talab qiladi, lokal server esa ichki tarmoqda. Worker kodni oladi va brauzerni lokal serverga qaytaradi (kod Workerda saqlanmaydi, faqat shaxsiy tarmoq manzillariga yo'naltiradi).
2. **Qisqa havolalar + kliklar hisobi** (UTM bilan).
3. **Vaqtinchalik ommaviy fayl** — Instagram rasm nashri uchun (nashrdan keyin o'chiriladi). Shu sabab **R2 (karta talab qiladi) odatda kerak emas**.

Bepul tarif: kuniga 100 000 so'rov, KV 1 GB — bu yetarli.

## 1. Akkaunt

dash.cloudflare.com da bepul akkaunt oching (karta shart emas). **Workers & Pages** bo'limiga kiring va `workers.dev` subdomeniningizni tanlang.

## 2. KV va D1 yaratish

- **Workers & Pages → KV → Create a namespace**: nomi `LINKS`.
- **Workers & Pages → D1 SQL Database → Create**: nomi `smm-db`. Ochilgach **Console** tabida quyidagini ishga tushiring:

```sql
CREATE TABLE IF NOT EXISTS clicks (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, t INTEGER, source TEXT, device TEXT, country TEXT);
CREATE INDEX IF NOT EXISTS idx_clicks_t ON clicks(t);
```

## 3. Worker yaratish

1. **Workers & Pages → Create → Create Worker** → nom: `smm-links` → Deploy.
2. **Edit code** → ichidagi hamma narsani o'chirib, loyiha papkasidagi `worker_cloudflare\worker.js` mazmunini joylang → **Deploy**.
3. **Settings → Bindings (Variables)**:
   - **KV namespace binding:** Variable name `LINKS` → namespace `LINKS`.
   - **D1 database binding:** Variable name `DB` → `smm-db`.
   - **Secret:** `ADMIN_TOKEN` — uzun tasodifiy qator (kamida 32 belgi). Parol menejerida generatsiya qiling.
4. Worker manzili: `https://smm-links.<akkaunt>.workers.dev` (Overview sahifasida).

## 4. Tizimda sozlash

*Sozlamalar → API kalitlar*:

- **Cloudflare Worker manzili** — yuqoridagi `https://...workers.dev` (oxirida `/` siz)
- **Worker admin tokeni** — 3-qadamdagi `ADMIN_TOKEN` bilan aynan bir xil

So'ng «Cloudflare Worker» tugmasini bosib tekshiring. «Havolalar» sahifasida yangi qisqa havola yarating va brauzerda oching.

## 5. OAuth callback manzillari

Meta va Google'da ro'yxatdan o'tkaziladigan redirect URI'lar:

- `https://smm-links.<akkaunt>.workers.dev/oauth/instagram/callback`
- `https://smm-links.<akkaunt>.workers.dev/oauth/youtube/callback`

Oqim: foydalanuvchi ruxsat beradi → Meta/Google brauzerni shu manzilga yuboradi → Worker brauzerni `http://<server-LAN-IP>:8000/oauth/.../done/` ga qaytaradi (faqat 10.x, 172.16–31.x, 192.168.x, localhost ruxsat) → tizim kodni tokenga almashtiradi. **Ulanishni boshlagan kompyuter tizim bilan bir tarmoqda bo'lishi kerak** (aks holda qaytish manzili ochilmaydi).

## 6. Rejalashtirilgan Reels/video/Stories va saqlash joyi

| Tur | Qanday yuboriladi | Qo'shimcha hosting kerakmi |
|---|---|---|
| Telegram (har qanday) | Bot API — fayl to'g'ridan-to'g'ri yuklanadi | Yo'q |
| YouTube video | To'g'ridan-to'g'ri yuklash | Yo'q |
| Instagram Reels/video/Stories | Rasmiy *resumable upload* — fayl to'g'ridan-to'g'ri yuklanadi | Yo'q |
| Instagram rasm/karusel | Ommaviy URL kerak → Worker KV vaqtinchalik | Worker KV (bepul) |

Ya'ni rejalashtirilgan video va Reels uchun hajm bo'yicha muammo yo'q: ular serverda (diskda) turadi va nashr vaqti kelganda yuklanadi. Server kompyuter nashr vaqtida **yoqilgan va internetga ulangan** bo'lishi shart (avtostartni yoqing).

Worker KV bitta qiymatga ~25 MB ruxsat beradi — rasmlar uchun yetarli. Ulkan rasm/video kerak bo'lsa tizim R2 ga o'tadi (ixtiyoriy, quyida).

## 7. R2 (ixtiyoriy)

Faqat Worker KV yetmaydigan holatlar uchun (juda katta fayllar). R2 bepul 10 GB beradi, lekin ro'yxatdan o'tishda to'lov kartasi so'raladi.

1. Cloudflare → **R2 → Create bucket** (`smm-temp`) → Bucket Settings → **Public access** yoqing (yoki custom domen).
2. **R2 → Manage R2 API tokens → Create API token** (Object Read & Write) → *Access Key ID* va *Secret Access Key* ni oling.
3. Tizimda *Sozlamalar → API kalitlar*: R2 Account ID, Access Key ID, Secret, Bucket.
4. *Sozlamalar → Nashr → Vaqtinchalik hosting*: `auto` (avval Worker KV, kerak bo'lsa R2).

Tizim R2 hajmini 9 GB bilan cheklaydi (bepul 10 GB dan oshib to'lov chiqmasligi uchun) va nashrdan keyin fayllarni o'chiradi.
