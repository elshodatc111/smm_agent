# 6. AI kalitlari (Gemini, Groq, OpenRouter) va o'zbekcha ovozni matnga o'tkazish

Tizim AI so'rovlarini **AI Router** orqali yuboradi: har vazifa (uzun matn, tasnif, rasm/video tahlili, ovoz→matn) uchun provayderlar ketma-ketligi bor. Bepul provayderdan ishlamasa yoki limit tugasa — keyingisiga o'tadi. Bir provayderga bir nechta kalit qo'shsangiz, navbat bilan ishlatiladi (limit taqsimlanadi).

## Qaysi provayderga nima

| Provayder | Narx | Nima uchun |
|---|---|---|
| **Google Gemini** | Bepul tarif (limitli) | Uzun o'zbekcha matn, brend xotirasi, rasm/video tahlili, STT zaxirasi |
| **Groq** | Bepul tarif | Tezkor tasnif (izoh sentimenti), **Whisper** ovoz→matn |
| **OpenRouter** | Bepul modellar bor (kuniga cheklangan) | Zaxira |
| **Claude (pullik)** | Pullik | **Standart holatda O'CHIQ.** Faqat siz yoqsangiz va byudjet qo'ysangiz ishlaydi |

Bepul tarif shartlari (limitlar, qaysi modellar bepul) tez-tez o'zgaradi — tizimdagi limit qiymatlari *Sozlamalar → AI router* da tahrirlanadi.

## Kalit olish

- **Gemini:** aistudio.google.com → *Get API key* → *Create API key*.
- **Groq:** console.groq.com → *API Keys* → *Create API Key*.
- **OpenRouter:** openrouter.ai → *Keys* → *Create Key*. Bepul modellarni ishlatish uchun nomi `:free` bilan tugaydigan modelni tanlang (Sozlamalar → AI router → Modellar).

## Tizimga kiritish

*Sozlamalar → AI router* sahifasi pastida **AI kalit qo'shish**: provayder, nom (masalan `gemini-1`), kalit → «Qo'shish». Kalit shifrlanadi, sahifalarda faqat maskalangan ko'rinishda (`AIza…x9`) chiqadi. Ikkinchi, uchinchi kalitni ham shu tarzda qo'shing (tavsiya: har provayderdan 2 tadan, **turli Google akkauntlaridan** — qoidalarga zid ko'p akkaunt ochmang, o'z hisobingizdan foydalaning).

## O'zbekcha uchun sifat nazorati

- Har bir AI javobi **o'zbek (lotin)** tilida ekanini tekshiruvdan o'tadi (kirill, rus yoki ingliz matn aralashsa — avtomatik qayta so'raladi, keyin boshqa provayderga o'tadi).
- Har bir biznesning **brend xotirasi** (ohang, taqiqlangan so'zlar, faktlar) har so'rovga qo'shiladi.
- AI yaratgan kontent **qoralama** belgisi bilan chiqadi va inson «ko'rib chiqdim» demaguncha nashr qilinmaydi.

## Ovoz → matn (STT): optimal zanjir

Videolardagi o'zbekcha nutqni matnga aylantirish ketma-ketligi:

1. **Groq Whisper (large-v3)** — tez va bepul, til `uz` ko'rsatiladi, o'zbek lotin uchun yo'naltiruvchi prompt bilan.
2. Natija ishonchliligi pasaysa (matn qisqa/takror/lotin-kirill aralash) → **Gemini** audio rejimi (ko'pincha o'zbekchani yaxshi tushunadi).
3. Ikkalasi ham xato bersa → **lokal Whisper** (`faster-whisper`, serverning o'zida; kartada GPU bo'lsa tez). O'rnatish: `.venv\Scripts\pip install faster-whisper` (ixtiyoriy, model birinchi marta ~500 MB yuklanadi). model o'lchami `media.local_whisper_model` sozlamasida (standart `small`).

Past ishonchli natija media tahlil sahifasida «qisman natija» deb belgilanadi — hech narsa jimgina yo'qolmaydi.

Haqiqat: o'zbek tili uchun barcha umumiy modellarning sifati ingliz tilidagidan past; muhim matnlarni nashrdan oldin o'qib chiqing. Sifat yetmasa, o'zbekchaga ixtisoslashgan xizmatlarni keyinroq provayder sifatida qo'shish mumkin (arxitektura shunga tayyor).

## Pullik Claude'ni yoqish (ixtiyoriy)

*Sozlamalar → AI router*: «Pullik AI (Claude) yoqilgan» → belgilang; Claude API kalitini kiriting; **oylik byudjet ($)** ni qo'ying; siyosat:
- `only_when_free_exhausted` — faqat bepul variantlar ishlamaganda (tavsiya);
- `quality_tasks` — sifat muhim vazifalar (brend, ssenariy);
- `always` — doim.

Byudjet tugasa Claude avtomatik o'chadi. Sarflangan summa «Tizim holati» da ko'rinadi.
