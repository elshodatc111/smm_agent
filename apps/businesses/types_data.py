"""Tizim biznes turlari: har tur o'z savollari (pasport maydonlari), faktlar uchun mavzular va reklama maslahatlariga ega.
Maydon: {key, label, kind: text|long|choice|number, help, choices}. Foydalanuvchi Sozlamalar → Biznes turlari bo'limida yangi tur qo'sha oladi."""
from __future__ import annotations

# Hamma turga umumiy savollar (pasportning «strategiya» bloki)
GENERAL_FIELDS = [
    {"key": "usp", "label": "Sizni boshqalardan ajratib turadigan 2–3 narsa", "kind": "long", "help": "Raqobatchilardan farqingiz: tezlik, narx, sifat, tajriba, kafolat."},
    {"key": "pain", "label": "Mijozning asosiy muammosi / og'rig'i", "kind": "long", "help": "Mijoz sizga nima uchun keladi? Qaysi muammoni hal qilasiz?"},
    {"key": "offer", "label": "Hozir eng ko'p sotmoqchi bo'lgan xizmat / mahsulot", "kind": "text", "help": "Tavsiyalar shu yo'nalishga ustuvorlik beradi."},
    {"key": "sales_process", "label": "Mijoz sizdan qanday sotib oladi?", "kind": "long", "help": "Qadamlar: ijtimoiy tarmoq → yozish → muloqot → to'lov → xizmat. Qayerda mijoz yo'qoladi?"},
    {"key": "proof", "label": "Ishonch omillari", "kind": "long", "help": "Natijalar, mijozlar soni, sertifikat, portfolio, sharhlar."},
    {"key": "tone", "label": "Muloqot ohangi", "kind": "choice", "choices": ["Do'stona", "Ekspert / jiddiy", "Rasmiy", "Hazil bilan", "Ilhomlantiruvchi"], "help": ""},
    {"key": "taboo", "label": "Nimani aytish / qilish mumkin emas", "kind": "long", "help": "Taqiqlangan so'zlar, mavzular, va'dalar."},
    {"key": "capacity", "label": "Kontent uchun imkoniyat", "kind": "text", "help": "Kim suratga oladi, haftasiga nechta post/video chiqara olasiz?"},
    {"key": "seasonality", "label": "Mavsumiylik", "kind": "text", "help": "Qaysi oylarda talab ko'tariladi/tushadi?"},
    {"key": "platform_roles", "label": "Har ijtimoiy tarmoqning vazifasi", "kind": "long", "help": "Masalan: Telegram — mijozlar bilan aloqa; Instagram — vizual portfolio; YouTube — darslar."},
]

CORE_KEYS = ["industry", "region", "description", "products", "price_range", "audience", "contact_info"]


def _f(key, label, kind="text", help="", choices=None):
    d = {"key": key, "label": label, "kind": kind, "help": help}
    if choices:
        d["choices"] = choices
    return d


TYPES: dict[str, dict] = {
    "shaxsiy_blog": {
        "name": "Shaxsiy brend / frilanser (dizayner, SMM, mutaxassis)", "sort": 1,
        "topics": ["graphic design", "branding", "social media marketing", "freelance", "content creation", "typography", "motion design"],
        "fields": [
            _f("specialty", "Asosiy mutaxassislik", "text", "Masalan: grafik dizayn, SMM, targetolog"),
            _f("services_list", "Xizmatlar ro'yxati va narxi", "long", "Har qatorda bittadan: xizmat — narx"),
            _f("portfolio", "Portfolio qayerda (havola)", "text", "Behance, Telegram kanal, Instagram highlight..."),
            _f("client_type", "Mijozlaringiz kim", "choice", "", ["Kichik biznes", "Individual mijozlar", "Agentliklar", "Korxonalar", "Aralash"]),
            _f("workflow", "Buyurtma bilan ishlash jarayoni", "long", "Brif → eskiz → tahrir → topshirish. Muddatlar."),
            _f("experience", "Tajriba va yutuqlar", "long"),
        ],
        "config": {"key_metrics": ["obunachi_osishi", "saqlash", "ulashish", "murojaat"],
                   "content_types": ["portfolio ishlar", "oldin-keyin", "jarayon (reels)", "maslahat va dars", "keys (natija bilan)", "shaxsiy hikoya", "mijoz sharhi", "narx va xizmatlar"],
                   "seasonality": "Yangi yil, Navro'z, bayramlar oldidan buyurtma ko'payadi; yozda biroz pasayish",
                   "defaults": {"ctr": 0.012, "click_to_lead": 0.05, "cpm": 22000},
                   "advice": "Shaxsiy brend: ko'proq jarayon va natija ko'rsating, foydali maslahat bering, har 3–4 postdan birida xizmat taklif qiling."},
    },
    "oquv_markaz": {
        "name": "O'quv markaz / kurslar", "sort": 2,
        "topics": ["online education", "learning", "teaching methods", "edtech", "career skills", "exam preparation"],
        "fields": [
            _f("courses", "Kurslar va davomiyligi", "long", "Har qatorda: kurs — davomiyligi — narxi"),
            _f("group_size", "Guruhdagi o'quvchilar soni", "text"),
            _f("teachers", "O'qituvchilar haqida", "long", "Tajribasi, yutuqlari"),
            _f("results", "O'quvchilar natijalari", "long", "Imtihon ballari, ish topganlar, sertifikatlar"),
            _f("enroll_period", "Qabul vaqtlari", "text", "Qachon yangi guruhlar boshlanadi?"),
            _f("format", "Dars formati", "choice", "", ["Oflayn", "Onlayn", "Aralash"]),
        ],
        "config": {"key_metrics": ["lead", "royxatga_olish", "kurs_tolovi"],
                   "content_types": ["reels", "natijalar", "o'qituvchi tanishuvi", "aksiya", "savol-javob"],
                   "seasonality": "Sentabr va yanvarda qabul avjida; yozda pasayish",
                   "defaults": {"ctr": 0.012, "click_to_lead": 0.06, "cpm": 25000},
                   "advice": "Lead va ro'yxatga olishga e'tibor; ota-onalar uchun ishonch kontenti."},
    },
    "restoran_kafe": {
        "name": "Restoran / kafe / ovqatlanish", "sort": 3,
        "topics": ["restaurant marketing", "food trends", "cafe business", "hospitality", "recipes", "food photography"],
        "fields": [
            _f("cuisine", "Oshxona turi", "text", "Milliy, fast-food, qahvaxona, desert..."),
            _f("signature", "Eng mashhur taomlar", "long"),
            _f("avg_bill", "O'rtacha hisob (bir mehmon)", "text"),
            _f("hours", "Ish vaqti va manzil", "text"),
            _f("delivery", "Yetkazib berish / bron", "choice", "", ["Faqat zalda", "Yetkazib berish bor", "Bron qilinadi", "Hammasi"]),
            _f("atmosphere", "Muhit va maxsus tadbirlar", "long"),
        ],
        "config": {"key_metrics": ["saqlash", "ulashish", "bron", "yetkazib_berish_buyurtma"],
                   "content_types": ["taom videosi", "menyu yangiligi", "aksiya", "mehmon sharhi", "oshxona ortidagi jarayon"],
                   "seasonality": "Hayit, Navro'z, Yangi yil, hafta oxirlari", "defaults": {"ctr": 0.015, "click_to_lead": 0.08, "cpm": 20000},
                   "advice": "Vizual taom kontenti, joy va vaqtni aniq ko'rsating."},
    },
    "onlayn_dokon": {
        "name": "Onlayn do'kon / savdo", "sort": 4,
        "topics": ["ecommerce", "retail marketing", "product photography", "customer experience", "online shopping trends"],
        "fields": [
            _f("catalog", "Mahsulot toifalari", "long"),
            _f("bestsellers", "Eng ko'p sotiladigan mahsulotlar", "long"),
            _f("delivery_terms", "Yetkazib berish va to'lov shartlari", "long"),
            _f("return_policy", "Qaytarish / kafolat", "text"),
            _f("order_channel", "Buyurtma qayerda qabul qilinadi", "choice", "", ["Telegram", "Instagram direct", "Veb-sayt", "Telefon", "Aralash"]),
        ],
        "config": {"key_metrics": ["saqlash", "ulashish", "katalog_kliklari", "buyurtma"],
                   "content_types": ["mahsulot taqdimoti", "aksiya", "mijoz sharhi", "qadoqlash jarayoni", "taqqoslash"],
                   "seasonality": "Hayit, 8-mart, Yangi yil, chegirma mavsumlari", "defaults": {"ctr": 0.015, "click_to_lead": 0.08, "cpm": 20000},
                   "advice": "Aniq narx va yetkazib berish; mijoz sharhlaridan ishonch yarating."},
    },
    "kiyim_dokoni": {
        "name": "Kiyim do'koni / moda", "sort": 5,
        "topics": ["fashion trends", "style", "retail fashion", "clothing care", "color trends"],
        "fields": [
            _f("brands", "Brendlar va uslublar", "long"),
            _f("sizes", "O'lchamlar va kolleksiyalar", "text"),
            _f("price_tiers", "Narx toifalari", "text"),
            _f("order_channel", "Buyurtma kanali", "choice", "", ["Do'kon", "Telegram", "Instagram direct", "Veb-sayt", "Aralash"]),
        ],
        "config": {"key_metrics": ["saqlash", "ulashish", "katalog_kliklari"],
                   "content_types": ["lookbook", "yangi kolleksiya", "aksiya", "mijoz sharhi", "reels (kiyib ko'rish)"],
                   "seasonality": "Mavsum almashuvi, Navro'z, Ramazon/Hayit, Yangi yil", "defaults": {"ctr": 0.015, "click_to_lead": 0.08, "cpm": 20000},
                   "advice": "Vizual kontent va aksiya; mahsulot katalogiga yo'naltirish."},
    },
    "xizmat_korsatish": {
        "name": "Xizmat ko'rsatish (ta'mirlash, tozalash, logistika, yuridik...)", "sort": 6,
        "topics": ["small business", "customer service", "service marketing", "local business", "home services"],
        "fields": [
            _f("service_list", "Xizmatlar va narxlar", "long"),
            _f("coverage", "Xizmat hududi", "text"),
            _f("response_time", "Javob va bajarish tezligi", "text"),
            _f("guarantee", "Kafolat va shartnoma", "text"),
            _f("client_kind", "Mijozlar", "choice", "", ["Jismoniy shaxslar", "Korxonalar", "Aralash"]),
        ],
        "config": {"key_metrics": ["murojaat", "javob_tezligi", "ishonch"],
                   "content_types": ["ish jarayoni", "oldin-keyin", "maslahat", "mijoz sharhi", "narx ro'yxati"],
                   "defaults": {"ctr": 0.01, "click_to_lead": 0.05, "cpm": 22000}, "advice": "Tezlik, kafolat va aniq narx ishonch beradi."},
    },
    "goza_salon": {
        "name": "Go'zallik saloni / barber / spa", "sort": 7,
        "topics": ["beauty trends", "hair care", "skincare", "salon business", "makeup"],
        "fields": [
            _f("services_price", "Xizmatlar va narxlar", "long"),
            _f("masters", "Ustalar va tajribasi", "long"),
            _f("booking", "Yozilish usuli", "choice", "", ["Telefon", "Telegram", "Instagram direct", "Onlayn bron"]),
            _f("hours", "Ish vaqti va manzil", "text"),
        ],
        "config": {"key_metrics": ["saqlash", "ulashish", "bron"], "content_types": ["oldin-keyin", "jarayon", "usta tanishuvi", "aksiya", "maslahat"],
                   "seasonality": "Bayramlar va to'ylar oldidan talab oshadi", "defaults": {"ctr": 0.015, "click_to_lead": 0.07, "cpm": 20000},
                   "advice": "Oldin-keyin kontenti va usta shaxsi ishonch beradi."},
    },
    "tibbiyot_klinika": {
        "name": "Tibbiyot / klinika / stomatologiya", "sort": 8,
        "topics": ["healthcare", "dentistry", "preventive medicine", "wellness", "medical technology"],
        "fields": [
            _f("specialties", "Yo'nalishlar va shifokorlar", "long"),
            _f("license", "Litsenziya va sertifikatlar", "text"),
            _f("price_policy", "Narx siyosati", "text", "Maslahat narxi, tekshiruv"),
            _f("booking", "Qabulga yozilish", "text"),
            _f("compliance", "Reklama cheklovlari (tibbiy va'dalar taqiqi)", "long", "Qonun bo'yicha nima aytilishi mumkin emas"),
        ],
        "config": {"key_metrics": ["murojaat", "qabulga_yozilish", "ishonch"], "content_types": ["shifokor tanishuvi", "foydali maslahat", "savol-javob", "jihozlar", "mijoz sharhi"],
                   "defaults": {"ctr": 0.01, "click_to_lead": 0.05, "cpm": 24000}, "advice": "Tibbiy va'dalardan saqlaning, ishonch va ekspertlikka tayaning."},
    },
    "it_kompaniya": {
        "name": "IT kompaniya / dasturlash / mobil ilova", "sort": 9,
        "topics": ["software development", "flutter", "backend", "mobile development", "startups", "ai tools", "cybersecurity"],
        "fields": [
            _f("products_it", "Mahsulot va xizmatlar", "long"),
            _f("stack", "Texnologiyalar", "text", "Python, Flutter, Django..."),
            _f("clients_b2b", "Mijozlar turi", "choice", "", ["B2B", "B2C", "Ikkalasi"]),
            _f("cases", "Loyiha keyslari", "long"),
            _f("pricing_model", "Narxlash modeli", "choice", "", ["Loyiha bo'yicha", "Soatbay", "Obuna", "Aralash"]),
        ],
        "config": {"key_metrics": ["lead", "obunachi_osishi", "ulashish"], "content_types": ["dars", "keys", "yangilik tahlili", "kod parchasi", "karyera maslahat"],
                   "defaults": {"ctr": 0.01, "click_to_lead": 0.04, "cpm": 25000}, "advice": "Ekspert kontent + keyslar; targetli lead yig'ish."},
    },
    "kochmas_mulk": {
        "name": "Ko'chmas mulk / qurilish", "sort": 10,
        "topics": ["real estate market", "construction", "interior design", "property investment", "architecture"],
        "fields": [
            _f("objects", "Obyektlar turi", "long"),
            _f("price_range_re", "Narx oralig'i", "text"),
            _f("regions_re", "Hududlar", "text"),
            _f("deal_terms", "Bitim shartlari (ipoteka, bo'lib to'lash)", "long"),
            _f("legal", "Hujjatlar va ishonch", "text"),
        ],
        "config": {"key_metrics": ["lead", "korishga_yozilish"], "content_types": ["obyekt turi (video)", "narx tahlili", "savol-javob", "mijoz sharhi", "yangi loyiha"],
                   "defaults": {"ctr": 0.008, "click_to_lead": 0.04, "cpm": 28000}, "advice": "Video tur va aniq shartlar; lead sifatiga e'tibor."},
    },
    "fitnes_sport": {
        "name": "Fitnes / sport / sog'lom turmush", "sort": 11,
        "topics": ["fitness", "workout science", "nutrition", "sports training", "wellness habits"],
        "fields": [
            _f("programs", "Dasturlar va abonementlar", "long"),
            _f("trainers", "Murabbiylar", "long"),
            _f("results_fit", "Mijoz natijalari", "long"),
            _f("schedule", "Jadval va manzil", "text"),
        ],
        "config": {"key_metrics": ["saqlash", "ulashish", "sinov_mashgulot"], "content_types": ["mashq", "natija", "murabbiy", "aksiya", "motivatsiya"],
                   "defaults": {"ctr": 0.015, "click_to_lead": 0.06, "cpm": 20000}, "advice": "Natija hikoyalari va qisqa mashq videolari."},
    },
    "kontent_yaratuvchi": {
        "name": "Bloger / kontent yaratuvchi / media", "sort": 12,
        "topics": ["content creation", "creator economy", "video editing", "social media growth", "storytelling"],
        "fields": [
            _f("niche", "Asosiy mavzu (niche)", "text"),
            _f("formats", "Asosiy formatlar", "text", "Video, podkast, matn..."),
            _f("monetization", "Daromad usullari", "long", "Reklama, hamkorlik, kurs, obuna"),
            _f("series", "Doimiy ruknlar", "long"),
        ],
        "config": {"key_metrics": ["obunachi_osishi", "korish", "ushlab_turish"], "content_types": ["rukn", "trend", "kamera ortida", "savol-javob"],
                   "defaults": {"ctr": 0.01, "click_to_lead": 0.03, "cpm": 20000}, "advice": "Doimiy ritm va ushlab turish (retention)."},
    },
    "boshqa": {
        "name": "Boshqa (o'zim sozlayman)", "sort": 99,
        "topics": [],
        "fields": [
            _f("what_we_do", "Biznes nima bilan shug'ullanadi", "long"),
            _f("key_numbers", "Muhim raqamlar", "long", "Mijozlar soni, narx, hajm"),
        ],
        "config": {"key_metrics": ["obunachi_osishi", "murojaat"], "content_types": [], "defaults": {"ctr": 0.012, "click_to_lead": 0.05, "cpm": 22000},
                   "advice": "Biznes turini Sozlamalar → Biznes turlari bo'limida aniqlashtiring."},
    },
    # eski kalit — mavjud bazalar uchun saqlanadi
    "kompyuter_xizmatlari": {
        "name": "Kompyuter xizmatlari", "sort": 13,
        "topics": ["it support", "hardware", "networking", "cybersecurity basics"],
        "fields": [
            _f("service_list", "Xizmatlar va narxlar", "long"),
            _f("response_time", "Javob tezligi", "text"),
            _f("client_kind", "Mijozlar", "choice", "", ["Jismoniy shaxslar", "Korxonalar", "Aralash"]),
        ],
        "config": {"key_metrics": ["murojaat", "javob_tezligi", "ishonch"], "content_types": ["ish jarayoni", "maslahat", "oldin-keyin", "B2B keys", "narx ro'yxati"],
                   "seasonality": "Hisobot davrlari (B2B), o'quv yili boshi (B2C)", "defaults": {"ctr": 0.01, "click_to_lead": 0.05, "cpm": 22000},
                   "advice": "Xizmat ishonchi va tez javob; B2B va B2C alohida xabarlar."},
    },
}
