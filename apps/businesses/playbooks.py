"""Biznes turlari bo'yicha kontent andozalari (playbook): kontent ustunlari, tayyor g'oyalar, karusel hikoya yo'llari,
mavsumiylik, CTA va ehtiyot qoidalari. Reja va karusel generatorlari shu andozadan boshlaydi, keyin AI uni aniq biznesga moslaydi.
Andozada narx, telefon, natija raqami YO'Q: ularni faqat biznes o'zi kiritadi («Aniq faktlar»)."""
from __future__ import annotations


def P(key, name, share, desc):
    return {"key": key, "name": name, "share": share, "desc": desc}


def I(pillar, topic, fmt, hook):  # noqa: E741
    return {"pillar": pillar, "topic": topic, "format": fmt, "hook": hook}


def A(name, arc):
    return {"name": name, "arc": arc}


# Karusel hikoya yo'llari uchun umumiy rollar: hook, muammo, burilish, yechim, dalil, natija, cta, qadam, xato, maslahat
DEFAULT = {
    "pillars": [
        P("talim", "Foydali maslahat va ta'lim", 30, "Mijozga haqiqiy foyda beradigan qisqa maslahat va tushuntirish."),
        P("ishonch", "Ishonch va natija", 25, "Ish jarayoni, mijoz fikri, jamoa, sertifikat va haqiqiy natijalar."),
        P("sotuv", "Taklif va sotuv", 20, "Xizmat/mahsulot taqdimoti, aksiya va murojaat chaqirig'i."),
        P("hayot", "Jamoa va ichki hayot", 15, "Kamera ortidagi voqealar, jamoa, kundalik ish."),
        P("interaktiv", "Savol-javob va muloqot", 10, "So'rovnoma, savol-javob, mijoz savollariga javob."),
    ],
    "ideas": [
        I("talim", "Mijozlar eng ko'p beradigan 5 ta savol va javoblari", "carousel", "Bu savolni har kuni eshitamiz"),
        I("ishonch", "Ish jarayoni: boshdan oxirigacha qanday ishlaymiz", "reel", "Buyurtma bizga shunday keladi"),
        I("sotuv", "Asosiy xizmatimiz kimga mos va nima beradi", "post", "Sizga aynan shu kerak bo'lishi mumkin"),
        I("hayot", "Jamoamiz bilan bir kun", "reel", "Kun boshlanishi bizda shunday"),
        I("interaktiv", "Savolingizni yozing: haftalik savol-javob", "story", "Bugun savollaringizga javob beramiz"),
        I("talim", "Tanlashda eng ko'p qilinadigan 3 ta xato", "carousel", "Shu xatoni qilmang"),
        I("ishonch", "Mijoz fikri: u bizga nima uchun kelgan edi", "post", "Mijozimiz nima dedi"),
        I("sotuv", "Bu oy maxsus taklif", "story", "Faqat shu hafta"),
    ],
    "angles": [
        A("Muammo va yechim", ["hook", "muammo", "oqibat", "burilish", "yechim", "natija", "cta"]),
        A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "xulosa", "cta"]),
        A("Qadamma-qadam", ["hook", "qadam", "qadam", "qadam", "qadam", "natija", "cta"]),
        A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "xato", "tavsiya", "cta"]),
    ],
    "seasonality": {1: "Yangi yil rejalari, yangi boshlanishlar", 9: "O'quv yili va faol mavsum boshlanishi", 12: "Yil yakuni, sovg'a va aksiyalar"},
    "cta": ["Telegramga yozing", "Savolingiz bo'lsa, izohda yozing", "Saqlab qo'ying, kerak bo'ladi"],
    "avoid": ["Tasdiqlanmagan raqam va va'dalar", "Boshqalarni yomonlash"],
}

PLAYBOOKS: dict[str, dict] = {
    "shaxsiy_blog": {
        "pillars": [
            P("portfolio", "Portfolio va ishlar", 30, "Bajarilgan ishlar, jarayon va natija ko'rsatiladi."),
            P("talim", "Maslahat va mini-darslar", 25, "Soha bo'yicha qisqa foydali bilimlar."),
            P("keys", "Keys va mijoz hikoyasi", 20, "Mijozda muammo nima edi, qanday hal qilindi."),
            P("shaxs", "Shaxsiy hikoya", 15, "Yo'lim, xatolarim, kundalik ish; ishonch uchun."),
            P("sotuv", "Xizmat va narx", 10, "Xizmat turlari, ish tartibi, ro'yxatga olish."),
        ],
        "ideas": [
            I("portfolio", "Bitta loyiha: brief'dan tayyor natijagacha", "carousel", "Bu loyiha qanday tug'ildi"),
            I("portfolio", "Oldin va keyin: bir ish ustida o'zgarish", "reel", "Oldin shunday edi"),
            I("talim", "Mijoz brief'ida eng ko'p yetishmaydigan 5 narsa", "carousel", "Brief yozayotganda buni unutmang"),
            I("talim", "Yangi boshlovchilar qiladigan 3 ta xato", "reel", "Boshida men ham shunday qilganman"),
            I("keys", "Keys: mijoz muammosi va uni hal qilish yo'li", "carousel", "Mijozim shunday so'rab keldi"),
            I("shaxs", "Qanday qilib shu kasbga keldim", "post", "Hammasi kichik bir qarordan boshlandi"),
            I("sotuv", "Men bilan ishlash tartibi: 4 qadam", "carousel", "Buyurtma berishdan oldin bilib oling"),
            I("shaxs", "Bir ish kunim", "reel", "Ish kunim soat nechada boshlanadi"),
        ],
        "angles": [A("Loyiha hikoyasi", ["hook", "mijoz muammosi", "birinchi g'oya", "to'siq", "burilish", "natija", "cta"]),
                   A("Oldin va keyin", ["hook", "oldin", "nima o'zgardi", "jarayon", "keyin", "xulosa", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "tavsiya", "cta"])],
        "seasonality": {1: "Yangi yil: yangi brend va sayt buyurtmalari", 9: "Biznes mavsumi boshlanishi, ko'p buyurtma", 11: "Aksiya va yil yakuni buyurtmalari"},
        "cta": ["Loyihangiz bo'yicha Telegramga yozing", "Portfolio'ni saqlab qo'ying", "Brief yuboring"],
        "avoid": ["Mijoz ruxsatisiz uning ishini ko'rsatish", "Tasdiqlanmagan natija va'dalari"],
    },
    "oquv_markaz": {
        "pillars": [
            P("talim", "Foydali dars va maslahat", 30, "Fan/til bo'yicha qisqa dars, xatolar, o'rganish usullari."),
            P("natija", "Natijalar va ishonch", 25, "O'quvchi yutuqlari, sertifikat, o'qituvchilar tajribasi (faqat haqiqiy)."),
            P("oqituvchi", "O'qituvchi va dars jarayoni", 15, "O'qituvchi tanishuvi, dars lavhalari, muhit."),
            P("sotuv", "Kurs va qabul", 20, "Kurslar, yangi guruh boshlanishi, ro'yxatga olish."),
            P("interaktiv", "Savol-javob va viktorina", 10, "Test, viktorina, tez-tez beriladigan savollar."),
        ],
        "ideas": [
            I("talim", "Boshlovchilar eng ko'p qiladigan 5 ta xato", "carousel", "Shu xato sizni ham to'xtatib turgan bo'lishi mumkin"),
            I("talim", "Kuniga 20 daqiqada o'rganish rejasi", "carousel", "Vaqtingiz kam bo'lsa ham o'rganish mumkin"),
            I("talim", "Bugungi so'z/qoida: 30 soniyada", "reel", "30 soniyada yangi narsa o'rganing"),
            I("natija", "O'quvchi hikoyasi: qayerdan boshlab, qayerga keldi", "carousel", "U noldan boshlagan edi"),
            I("oqituvchi", "O'qituvchimiz bilan tanishing", "reel", "Sizni kim o'qitadi"),
            I("oqituvchi", "Dars qanday o'tadi: bir dars lavhasi", "reel", "Darsimizga bir qarang"),
            I("sotuv", "Yangi guruhga qabul: kim uchun va qachon", "post", "Yangi guruh ochilmoqda"),
            I("interaktiv", "Mini-test: bilimingizni sinang", "story", "5 ta savol, 1 daqiqa"),
            I("natija", "Imtihonga tayyorlanish bo'yicha 7 kunlik reja", "carousel", "Imtihongacha oz qoldi"),
        ],
        "angles": [A("O'quvchi hikoyasi", ["hook", "boshlanish", "qiyinchilik", "burilish", "o'rganish yo'li", "natija", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "xato", "to'g'ri yo'l", "cta"]),
                   A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "xulosa", "cta"]),
                   A("Haftalik reja", ["hook", "1-kun", "2-kun", "3-kun", "4-kun", "natija", "cta"])],
        "seasonality": {1: "Yangi yil rejalari: til/kasb o'rganish", 5: "Yoz oldi: intensiv kurslar", 8: "Yangi o'quv yiliga tayyorgarlik", 9: "Qabul avjida"},
        "cta": ["Bepul sinov darsiga yozilish uchun Telegramga yozing", "Savolingiz bo'lsa yozing", "Do'stingizga yuboring"],
        "avoid": ["Imtihondan o'tishga kafolat berish", "Tasdiqlanmagan natija foizlari", "Boshqa markazlarni yomonlash"],
    },
    "restoran_kafe": {
        "pillars": [
            P("taom", "Taom va menyu", 35, "Taomlar, yangi menyu, tayyorlanishi, mazasi."),
            P("jarayon", "Oshxona ortidagi jarayon", 20, "Oshpaz, masalliq, tayyorlash jarayoni."),
            P("mehmon", "Mehmonlar va muhit", 20, "Mehmon fikri, interer, tadbirlar."),
            P("sotuv", "Aksiya va bron", 15, "Aksiya, kunlik taklif, stol band qilish."),
            P("interaktiv", "Savol va o'yin", 10, "Qaysi taomni tanlaysiz, so'rovnoma."),
        ],
        "ideas": [
            I("taom", "Haftaning eng ko'p buyurtma qilingan taomi", "reel", "Bu taomni hamma so'raydi"),
            I("taom", "Yangi taom: qanday tayyorlanadi", "reel", "Menyuda yangilik bor"),
            I("jarayon", "Oshpazimiz bilan bir kun", "reel", "Oshxona ichida nima bo'ladi"),
            I("jarayon", "Masalliqlar qayerdan va qanday tanlanadi", "carousel", "Mazaning boshlanishi masalliqdan"),
            I("mehmon", "Mehmonimiz fikri", "post", "Mehmonlarimiz nima deydi"),
            I("mehmon", "Oilaviy kechki ovqat uchun 5 ta taom", "carousel", "Oilaviy kecha rejasi"),
            I("sotuv", "Bugungi kun taklifi", "story", "Faqat bugun"),
            I("interaktiv", "Qaysi birini tanlaysiz: A yoki B", "story", "Bitta tanlang"),
        ],
        "angles": [A("Taom hikoyasi", ["hook", "masalliq", "tayyorlash", "sirli qadam", "tayyor taom", "qanday yeyiladi", "cta"]),
                   A("Eng yaxshi 5 taom", ["hook", "taom", "taom", "taom", "taom", "taom", "cta"]),
                   A("Bir kun oshxonada", ["hook", "ertalab", "tushlik", "kechki payt", "yakun", "cta"])],
        "seasonality": {3: "Navro'z va bahor menyusi", 6: "Yozgi ichimlik va salatlar", 12: "Yangi yil bronlari va banketlar"},
        "cta": ["Stol band qilish uchun yozing", "Menyuni saqlab qo'ying", "Do'stlaringizni taklif qiling"],
        "avoid": ["Tasdiqlanmagan chegirma", "Allergen haqida noto'g'ri ma'lumot"],
    },
    "onlayn_dokon": {
        "pillars": [
            P("mahsulot", "Mahsulot taqdimoti", 35, "Mahsulot, xususiyatlari, qanday foydalaniladi."),
            P("tanlash", "Tanlash bo'yicha maslahat", 20, "Qanday tanlash, taqqoslash, xatolar."),
            P("ishonch", "Ishonch va xizmat", 20, "Qadoqlash, yetkazib berish, mijoz fikri, qaytarish."),
            P("sotuv", "Aksiya va yangi tovar", 15, "Chegirma, yangi kelgan tovarlar."),
            P("interaktiv", "Savol va o'yin", 10, "So'rovnoma, tanlov, mijoz savollari."),
        ],
        "ideas": [
            I("mahsulot", "Eng ko'p sotiladigan 5 ta mahsulot", "carousel", "Mijozlar eng ko'p shuni oladi"),
            I("mahsulot", "Mahsulotni ochamiz: ichida nima bor", "reel", "Buyurtma kelganda shunday ko'rinadi"),
            I("tanlash", "Tanlashda 3 ta muhim narsa", "carousel", "Sotib olishdan oldin buni tekshiring"),
            I("ishonch", "Buyurtma qadoqlanishi: boshidan oxirigacha", "reel", "Buyurtmangiz shunday yo'lga chiqadi"),
            I("ishonch", "Yetkazib berish qanday ishlaydi", "carousel", "Buyurtmadan eshikkacha"),
            I("sotuv", "Yangi kelgan tovarlar", "post", "Yangi tovarlar keldi"),
            I("interaktiv", "Qaysi rangni tanlaysiz", "story", "Sizning tanlovingiz"),
            I("tanlash", "Ikki mahsulot taqqoslanadi", "carousel", "Qaysi biri sizga mos"),
        ],
        "angles": [A("Mahsulot hikoyasi", ["hook", "muammo", "mahsulot", "qanday ishlaydi", "afzallik", "foydalanish", "cta"]),
                   A("Taqqoslash", ["hook", "birinchi variant", "ikkinchi variant", "farqi", "kimga qaysi biri", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "tavsiya", "cta"])],
        "seasonality": {3: "8-mart sovg'alari", 11: "Katta chegirmalar mavsumi", 12: "Yangi yil sovg'alari"},
        "cta": ["Buyurtma uchun Telegramga yozing", "Savolingiz bo'lsa yozing", "Saqlab qo'ying"],
        "avoid": ["Tasdiqlanmagan chegirma va muddat", "Mavjud bo'lmagan tovarni taklif qilish"],
    },
    "kiyim_dokoni": {
        "pillars": [
            P("lookbook", "Lookbook va yangi kolleksiya", 35, "Kiyim kombinatsiyalari, yangi kelganlar."),
            P("stil", "Stil maslahati", 25, "Qanday kiyinish, rang va mavsum bo'yicha tavsiya."),
            P("ishonch", "Mijoz va sifat", 15, "Mijoz fikri, mato, o'lcham tanlash."),
            P("sotuv", "Aksiya va buyurtma", 15, "Chegirma, yangi kolleksiya e'loni."),
            P("interaktiv", "Savol va tanlov", 10, "So'rovnoma, qaysi kiyim yoqadi."),
        ],
        "ideas": [
            I("lookbook", "Bitta kiyim, 3 xil kombinatsiya", "reel", "Bitta kiyim, uch xil ko'rinish"),
            I("lookbook", "Yangi kolleksiya: eng yaxshi 6 ta look", "carousel", "Yangi kolleksiya keldi"),
            I("stil", "Mavsumga mos 5 ta rang", "carousel", "Bu mavsum shu ranglar"),
            I("stil", "O'lchamni to'g'ri tanlash", "carousel", "Kiyim yarashmasa, sabab o'lchamda"),
            I("ishonch", "Mato va tikuv: sifatni qanday tekshirish", "reel", "Sifatni shu yerdan bilasiz"),
            I("sotuv", "Haftaning tanlangan kiyimlari", "story", "Bu hafta tanlovimiz"),
            I("interaktiv", "Qaysi look yoqdi: 1 yoki 2", "story", "Siz tanlang"),
        ],
        "angles": [A("Look hikoyasi", ["hook", "tadbir", "birinchi look", "ikkinchi look", "uchinchi look", "tanlov", "cta"]),
                   A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "xulosa", "cta"]),
                   A("Oldin va keyin", ["hook", "oddiy kiyim", "almashtirdik", "natija", "cta"])],
        "seasonality": {3: "Bahor kolleksiyasi va 8-mart", 9: "Kuz mavsumi", 12: "Yangi yil liboslari"},
        "cta": ["O'lcham va buyurtma uchun yozing", "Saqlab qo'ying", "Do'stingizga yuboring"],
        "avoid": ["Mavjud bo'lmagan o'lcham/rang va'dasi", "Tasdiqlanmagan chegirma"],
    },
    "xizmat_korsatish": {
        "pillars": [
            P("jarayon", "Ish jarayoni", 30, "Ish qanday bajariladi: boshidan oxirigacha."),
            P("natija", "Oldin va keyin", 25, "Bajarilgan ishlar natijasi."),
            P("talim", "Maslahat va xatolar", 20, "Mijozga foydali maslahat, tez-tez uchraydigan xatolar."),
            P("ishonch", "Ishonch va kafolat", 15, "Mijoz fikri, jamoa, ish shartlari."),
            P("sotuv", "Xizmat va buyurtma", 10, "Xizmat turlari, qanday buyurtma beriladi."),
        ],
        "ideas": [
            I("jarayon", "Bir buyurtma: chaqiruvdan tugagunigacha", "reel", "Buyurtma bizga shunday keladi"),
            I("natija", "Oldin va keyin: bir ish natijasi", "carousel", "Natijaga qarang"),
            I("talim", "Mijozlar eng ko'p qiladigan 5 ta xato", "carousel", "Uyda shuni qilmang"),
            I("ishonch", "Ustalarimiz bilan tanishing", "reel", "Sizning uyingizga kim keladi"),
            I("sotuv", "Xizmatlarimiz va qanday buyurtma beriladi", "post", "Buyurtma berish juda oson"),
            I("talim", "Muammo kelib chiqishidan oldin tekshirish ro'yxati", "carousel", "Buni oldindan tekshiring"),
        ],
        "angles": [A("Buyurtma hikoyasi", ["hook", "mijoz muammosi", "tekshiruv", "ish jarayoni", "natija", "mijoz fikri", "cta"]),
                   A("Oldin va keyin", ["hook", "oldin", "nima qildik", "jarayon", "keyin", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "tavsiya", "cta"])],
        "seasonality": {},
        "cta": ["Buyurtma uchun yozing yoki qo'ng'iroq qiling", "Savol bo'lsa yozing", "Saqlab qo'ying"],
        "avoid": ["Tasdiqlanmagan kafolat muddati va narx", "Mijozning shaxsiy ma'lumotini ko'rsatish"],
    },
    "goza_salon": {
        "pillars": [
            P("natija", "Oldin va keyin", 30, "Xizmat natijasi (mijoz roziligi bilan)."),
            P("jarayon", "Jarayon va ustalar", 25, "Usta ishi, vositalar, jarayon."),
            P("talim", "Parvarish maslahati", 20, "Uyda parvarish, xatolar, trendlar."),
            P("sotuv", "Aksiya va yozilish", 15, "Xizmat turlari, bo'sh vaqtlar, aksiya."),
            P("interaktiv", "Savol va tanlov", 10, "Qaysi stil yoqadi, so'rovnoma."),
        ],
        "ideas": [
            I("natija", "Bir mijoz: oldin va keyin", "reel", "O'zgarishga qarang"),
            I("jarayon", "Ustamiz ishlashi: 30 soniyada", "reel", "Usta qo'li bilan"),
            I("talim", "Uyda parvarish bo'yicha 5 ta maslahat", "carousel", "Uyda buni qiling"),
            I("talim", "Bu mavsumning trend ranglari/stillari", "carousel", "Bu mavsum trendi"),
            I("sotuv", "Bo'sh vaqtlar va yozilish", "story", "Bu hafta bo'sh vaqtlar"),
            I("interaktiv", "Qaysi stil yoqadi: A yoki B", "story", "Tanlang"),
        ],
        "angles": [A("Mijoz o'zgarishi", ["hook", "mijoz istagi", "tanlov", "jarayon", "natija", "cta"]),
                   A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "xulosa", "cta"]),
                   A("Parvarish qadamlari", ["hook", "qadam", "qadam", "qadam", "qadam", "natija", "cta"])],
        "seasonality": {3: "8-mart va bahor", 5: "To'y mavsumi", 12: "Yangi yil oldi: bandlik ko'p"},
        "cta": ["Yozilish uchun Telegramga yozing", "Saqlab qo'ying", "Do'stingizni olib keling"],
        "avoid": ["Mijoz roziligisiz foto", "Tibbiy natija kafolati"],
    },
    "tibbiyot_klinika": {
        "pillars": [
            P("talim", "Foydali tibbiy maslahat", 35, "Umumiy sog'liq bo'yicha tushuntirish (davolash va'dasisiz)."),
            P("shifokor", "Shifokor va jamoa", 20, "Shifokor tanishuvi, mutaxassislik."),
            P("jarayon", "Jihoz va jarayon", 15, "Tekshiruv qanday o'tadi, jihozlar."),
            P("savol", "Savol-javob", 20, "Bemorlarning tez-tez beriladigan savollari."),
            P("sotuv", "Qabul va yozilish", 10, "Xizmat turlari, qanday yozilish."),
        ],
        "ideas": [
            I("talim", "Tekshiruvga qachon borish kerak: 5 ta belgi", "carousel", "Bu belgilarni e'tiborsiz qoldirmang"),
            I("shifokor", "Shifokorimiz bilan tanishing", "reel", "Sizni kim qabul qiladi"),
            I("savol", "Bemorlar eng ko'p so'raydigan savollar", "carousel", "Bu savolga har kuni javob beramiz"),
            I("jarayon", "Birinchi qabul qanday o'tadi", "reel", "Qabulga kelsangiz nima bo'ladi"),
            I("talim", "Kundalik odatlar: sog'liq uchun 5 ta qoida", "carousel", "Kichik odatlar katta farq"),
            I("sotuv", "Qabulga yozilish tartibi", "post", "Yozilish juda oson"),
        ],
        "angles": [A("Savol-javob", ["hook", "savol", "javob", "savol", "javob", "xulosa", "cta"]),
                   A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "shifokor maslahati", "cta"]),
                   A("Belgilar ro'yxati", ["hook", "belgi", "belgi", "belgi", "qachon shifokorga", "cta"])],
        "seasonality": {1: "Shamollash mavsumi", 5: "Yozga tayyorgarlik", 9: "Maktab oldi tekshiruvlari"},
        "cta": ["Qabulga yozilish uchun yozing", "Savolingizni yozing", "Saqlab qo'ying"],
        "avoid": ["Davolash va natija kafolati", "Tashxis qo'yish (masofadan)", "Bemorning shaxsiy ma'lumoti", "Litsenziyasiz tibbiy va'dalar"],
    },
    "it_kompaniya": {
        "pillars": [
            P("talim", "Dars va texnik maslahat", 30, "Texnologiya bo'yicha qisqa darslar va maslahat."),
            P("keys", "Keys va loyihalar", 25, "Bajarilgan loyiha, muammo va yechim."),
            P("jamoa", "Jamoa va jarayon", 15, "Dasturchilar, ish usuli."),
            P("yangilik", "Texnologiya tahlili", 15, "Yangi vositalar va ularning biznesga ta'siri."),
            P("sotuv", "Xizmat va hamkorlik", 15, "Xizmat turlari, hamkorlik tartibi."),
        ],
        "ideas": [
            I("talim", "Biznes uchun mobil ilova kerakmi: 5 ta savol", "carousel", "Ilova kerakmi yoki sayt yetarlimi"),
            I("keys", "Loyiha hikoyasi: g'oyadan ishga tushirishgacha", "carousel", "Bu loyiha shunday boshlangan"),
            I("jamoa", "Jamoamiz bilan bir ish kuni", "reel", "Dasturchilar kuni"),
            I("talim", "Mijoz buyurtma berishdan oldin bilishi kerak bo'lgan 5 narsa", "carousel", "Texnik topshiriq nima uchun kerak"),
            I("yangilik", "Yangi texnologiya: oddiy tilda", "reel", "Bu yangilik sizga nima beradi"),
            I("sotuv", "Biz bilan ishlash bosqichlari", "carousel", "Loyiha qanday boshlanadi"),
        ],
        "angles": [A("Loyiha hikoyasi", ["hook", "mijoz muammosi", "g'oya", "to'siq", "yechim", "natija", "cta"]),
                   A("Qadamma-qadam", ["hook", "qadam", "qadam", "qadam", "qadam", "natija", "cta"]),
                   A("Mif va haqiqat", ["hook", "mif", "haqiqat", "mif", "haqiqat", "xulosa", "cta"])],
        "seasonality": {1: "Yangi yil: biznes raqamlashtirish rejalari", 9: "Yangi loyihalar mavsumi"},
        "cta": ["Loyiha bo'yicha yozing", "Bepul maslahat uchun yozing", "Saqlab qo'ying"],
        "avoid": ["Tasdiqlanmagan muddat va narx", "Mijoz ma'lumotini oshkor qilish", "Texnik atamalarni tushuntirmasdan ishlatish"],
    },
    "kochmas_mulk": {
        "pillars": [
            P("obyekt", "Obyektlar", 35, "Uy, xonadon, loyihalar taqdimoti."),
            P("talim", "Xaridor uchun maslahat", 25, "Qanday tanlash, hujjatlar, xatolar."),
            P("bozor", "Bozor va hududlar", 15, "Hudud tahlili, umumiy bozor holati."),
            P("ishonch", "Mijoz va jarayon", 15, "Bitim qanday o'tadi, mijoz fikri."),
            P("sotuv", "Taklif va ko'rishga yozilish", 10, "Yangi obyektlar, ko'rishga yozilish."),
        ],
        "ideas": [
            I("obyekt", "Obyekt turi: ichkarisiga sayohat", "reel", "Ichkariga kiramiz"),
            I("talim", "Xonadon sotib olishdan oldin tekshiriladigan 7 narsa", "carousel", "Sotib olishdan oldin buni tekshiring"),
            I("bozor", "Hududlar taqqoslanadi: qaysi biri kimga mos", "carousel", "Qaysi hudud sizga mos"),
            I("ishonch", "Bitim qadamlari: boshidan oxirigacha", "carousel", "Bitim shunday o'tadi"),
            I("obyekt", "Yangi obyekt: kimga mos", "post", "Yangi obyekt"),
            I("talim", "Birinchi xaridor qiladigan 5 xato", "carousel", "Birinchi uy: xatolar"),
        ],
        "angles": [A("Obyekt hikoyasi", ["hook", "kimga mo'ljallangan", "joylashuv", "ichkarisi", "afzallik", "bitim sharti", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "tavsiya", "cta"]),
                   A("Taqqoslash", ["hook", "birinchi variant", "ikkinchi variant", "farqi", "xulosa", "cta"])],
        "seasonality": {3: "Bahor: bozor jonlanadi", 9: "Kuz: ko'p bitimlar"},
        "cta": ["Ko'rishga yozilish uchun yozing", "Savolingizni yozing", "Saqlab qo'ying"],
        "avoid": ["Tasdiqlanmagan narx va daromad va'dasi", "Hujjatsiz obyekt taklifi"],
    },
    "fitnes_sport": {
        "pillars": [
            P("mashq", "Mashq va texnika", 35, "Mashq texnikasi, dastur, xatolar."),
            P("natija", "Natija va motivatsiya", 20, "O'quvchi yo'li (mijoz roziligi bilan), motivatsiya."),
            P("ovqat", "Ovqatlanish va odat", 15, "Sog'lom odatlar, ovqatlanish maslahati."),
            P("murabbiy", "Murabbiy va zal", 15, "Murabbiy tanishuvi, zal muhiti."),
            P("sotuv", "Abonement va sinov", 15, "Dasturlar, sinov mashg'uloti."),
        ],
        "ideas": [
            I("mashq", "Uyda 15 daqiqalik mashq", "reel", "Zalga bormasdan ham mumkin"),
            I("mashq", "Boshlovchilar qiladigan 5 ta xato", "carousel", "Shu xato jarohatga olib keladi"),
            I("ovqat", "Kunlik sog'lom odatlar ro'yxati", "carousel", "Kichik odatlar katta natija"),
            I("natija", "Mijoz yo'li: boshlangandan hozirgacha", "carousel", "U ham boshida qiynalgan"),
            I("murabbiy", "Murabbiyimiz bilan tanishing", "reel", "Sizni kim mashq qildiradi"),
            I("sotuv", "Sinov mashg'ulotiga yozilish", "story", "Birinchi mashg'ulot"),
        ],
        "angles": [A("Mijoz yo'li", ["hook", "boshlanish", "qiyinchilik", "burilish", "odat", "natija", "cta"]),
                   A("Haftalik reja", ["hook", "1-kun", "2-kun", "3-kun", "4-kun", "natija", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "to'g'ri texnika", "cta"])],
        "seasonality": {1: "Yangi yil va yangi odatlar: eng kuchli mavsum", 4: "Yozga tayyorgarlik", 9: "Maktab/ish mavsumi, qaytish"},
        "cta": ["Sinov mashg'ulotiga yozing", "Saqlab qo'ying", "Do'stingizni olib keling"],
        "avoid": ["Aniq vazn yo'qotish va'dasi", "Tibbiy maslahat berish", "Mijoz roziligisiz foto"],
    },
    "kontent_yaratuvchi": {
        "pillars": [
            P("rukn", "Doimiy ruknlar", 35, "Har hafta takrorlanadigan seriya (kuzatuvchi kutadi)."),
            P("trend", "Trend va yangilik", 20, "Dolzarb mavzu, o'z qarashim."),
            P("kamera", "Kamera ortida", 15, "Yaratish jarayoni, kundalik."),
            P("muloqot", "Savol-javob va jamoa", 20, "Kuzatuvchilar bilan muloqot."),
            P("hamkor", "Hamkorlik va reklama", 10, "Hamkor mahsulot/xizmat (halol ko'rsatiladi)."),
        ],
        "ideas": [
            I("rukn", "Haftalik rukn: yangi son", "reel", "Haftalik rukn qaytdi"),
            I("trend", "Bu hafta nima trend va menimcha nima uchun", "reel", "Hamma shu haqida gapiryapti"),
            I("kamera", "Bitta videoni qanday yarataman", "carousel", "Video orqasidagi ish"),
            I("muloqot", "Savollaringizga javob beraman", "story", "Savollarni yozing"),
            I("rukn", "Eng yaxshi 5 ta: to'plam", "carousel", "Bu hafta tanlovim"),
            I("hamkor", "Hamkor mahsulot: halol fikrim", "reel", "Sinab ko'rdim"),
        ],
        "angles": [A("Shaxsiy hikoya", ["hook", "boshlanish", "qiyinchilik", "burilish", "saboq", "cta"]),
                   A("Eng yaxshi 5 ta", ["hook", "birinchisi", "ikkinchisi", "uchinchisi", "to'rtinchisi", "beshinchisi", "cta"]),
                   A("Kamera ortida", ["hook", "g'oya", "tayyorgarlik", "suratga olish", "montaj", "natija", "cta"])],
        "seasonality": {1: "Yangi yil rejalari", 12: "Yil yakuni sarhisobi"},
        "cta": ["Obuna bo'ling", "Do'stingizga yuboring", "Izohda fikringizni yozing"],
        "avoid": ["Reklamani yashirish (hamkorlik ochiq aytilsin)", "Tasdiqlanmagan da'volar"],
    },
    "boshqa": DEFAULT,
    "kompyuter_xizmatlari": {
        "pillars": [
            P("talim", "Maslahat va xavfsizlik", 30, "Kompyuter, tarmoq, xavfsizlik bo'yicha oddiy maslahat."),
            P("jarayon", "Ish jarayoni", 25, "Ta'mirlash, o'rnatish, sozlash jarayoni."),
            P("natija", "Oldin va keyin", 20, "Tezlashtirilgan, tiklangan, yig'ilgan kompyuter."),
            P("b2b", "Korxonalar uchun xizmat", 15, "Ofis tarmog'i, abonent xizmati, qo'llab-quvvatlash."),
            P("sotuv", "Xizmat va narx tartibi", 10, "Xizmatlar, chaqirish tartibi."),
        ],
        "ideas": [
            I("talim", "Kompyuter sekin ishlashining 5 ta sababi", "carousel", "Kompyuteringiz shuning uchun sekin"),
            I("talim", "Ma'lumotni yo'qotmaslik uchun 4 qoida", "carousel", "Bir kun hammasi yo'qolishi mumkin"),
            I("jarayon", "Ta'mirlash jarayoni: qabuldan topshirishgacha", "reel", "Kompyuter bizga shunday keladi"),
            I("natija", "Oldin va keyin: tozalash va yangilash", "reel", "Natijaga qarang"),
            I("b2b", "Ofis uchun IT xizmati nima beradi", "carousel", "Ofisingiz to'xtab qolmasligi uchun"),
            I("sotuv", "Chaqirish va qabul tartibi", "post", "Xizmat buyurtma qilish"),
        ],
        "angles": [A("Muammo va yechim", ["hook", "muammo", "sabab", "tekshiruv", "yechim", "natija", "cta"]),
                   A("Xatolar ro'yxati", ["hook", "xato", "xato", "xato", "tavsiya", "cta"]),
                   A("Qadamma-qadam", ["hook", "qadam", "qadam", "qadam", "natija", "cta"])],
        "seasonality": {9: "O'quv yili: talabalar uchun kompyuter", 1: "Yangi yil: korxona IT rejalari"},
        "cta": ["Buyurtma uchun yozing", "Ofis uchun taklif so'rang", "Saqlab qo'ying"],
        "avoid": ["Ma'lumotni tiklashga 100% kafolat", "Mijoz ma'lumotini oshkor qilish"],
    },
}


PLAYBOOKS["boshqa"] = DEFAULT  # «Boshqa» tur: umumiy andoza


def playbook_for(business) -> dict:
    t = getattr(business, "template", None)
    return PLAYBOOKS.get(t.key if t else "", DEFAULT)
