"""«Qanday yoqish kerak» qo'llanmalari. Platforma interfeysi o'zgarib turadi, shuning uchun har qo'llanmada tekshirilgan sana ko'rsatiladi
va rasmiy yordam sahifasi bilan solishtirish tavsiya etiladi. Reklamani targetolog o'zi yoqadi — bu faqat yo'l-yo'riq."""
from __future__ import annotations

CHECKED = "2026-10"

TELEGRAM_COMMON = [
    ("Telegram Ads kabinetiga kiring", "ads.telegram.org saytida Telegram akkauntingiz bilan kiring va reklama akkauntini oching. Reklama beruvchi sifatida tasdiqlash talab qilinishi mumkin."),
    ("Yangi reklama yarating", "«New Ad» (Yangi reklama) bo'limida reklama turini tanlang: kanalga obunachi jalb qilish yoki post/havolani ko'rsatish."),
    ("Havolani belgilang", "Kanal havolasi (t.me/kanal) yoki aniq post havolasi (t.me/kanal/123) ni kiriting. Sotuv/lid uchun qisqa havola (UTM) ishlatsangiz, natijani o'lchay olasiz."),
    ("Reklama matni", "Matn qisqa (Telegram Ads cheklovi taxminan 160 belgi) va bitta aniq xabarga ega bo'lsin. Matnni o'zingiz yozing; taklif sahifasidagi xabar yo'nalishlari yordam beradi."),
    ("Auditoriyani tanlang", "Kanallar, mavzular va til bo'yicha nishonlang. Boshida kengroq, natijadan keyin toraytiring."),
    ("Narx va muddat", "Taklif narxi (CPM) va kunlik/umumiy limitni targetolog belgilaydi. Boshida kichik sinov, so'ng kengaytirish."),
    ("Tekshiring va yuboring", "Reklama moderatsiyadan o'tadi. Tasdiqlangach, birinchi kunlarda natijani kuzating."),
]
INSTAGRAM_COMMON = [
    ("Professional akkaunt", "Instagram akkauntingiz Professional (Business/Creator) bo'lishi kerak. Ilovada: Sozlamalar → Akkaunt turi."),
    ("Video/reelsni tanlang", "Reklama qilmoqchi bo'lgan reels yoki videoni oching va «Boost» (Reklama qilish) tugmasini bosing."),
    ("Maqsadni tanlang", "Taklif sahifasida ko'rsatilgan maqsadga mos variantni tanlang (profil tashriflari, xabarlar, sayt tashriflari yoki ko'rishlar)."),
    ("Auditoriya", "Avval «Avtomatik»ni sinab ko'ring; keyin joylashuv, yosh va qiziqishlar bo'yicha qo'lda toraytiring."),
    ("Byudjet va muddat", "Byudjet va kunlarni targetolog belgilaydi. Birinchi sinov uchun qisqa muddat (3–5 kun) tavsiya etiladi."),
    ("Ko'rib chiqish va yuborish", "Reklama tekshiruvdan o'tadi. Faollikni «Insights → Reklama» bo'limida kuzating."),
]
GUIDES = {
    "telegram": {"title": "Telegram Ads orqali yoqish", "url": "https://ads.telegram.org", "steps": TELEGRAM_COMMON,
                 "tips": ["Bir vaqtning o'zida faqat bitta narsani o'zgartiring (matn yoki auditoriya).", "Natijani kamida 3–5 kun kuzating.", "Kanal tavsifi va mahkamlangan post reklamadan oldin tayyor bo'lsin."]},
    "instagram": {"title": "Instagram'da Boost orqali yoqish", "url": "https://help.instagram.com", "steps": INSTAGRAM_COMMON,
                  "tips": ["Videoning birinchi 3 soniyasi hal qiluvchi.", "Profil bio, highlight va oxirgi 9 post tartibli bo'lsin: reklama profilga olib keladi.", "To'lov usuli va hududingizda reklama imkoniyati borligini oldindan tekshiring."]},
}
OBJECTIVE_NOTES = {
    "subscribers": "Maqsad — yangi obunachi: reklama kanalga/profilga obuna bo'lishga undasin.",
    "views": "Maqsad — ko'rish: eng ushlab turuvchi qisqa kontentni tanlang.",
    "leads": "Maqsad — murojaat: har reklamada bitta aniq harakat (yozish yoki bosish).",
    "sales": "Maqsad — sotuv: narx/taklif va ishonch omillari aniq ko'rsatilsin.",
    "profile": "Maqsad — profil tashrifi: profil tayyor bo'lsin.",
}


def guide_for(platform: str, objective: str) -> dict:
    g = GUIDES.get(platform) or GUIDES["telegram"]
    return {**g, "objective_note": OBJECTIVE_NOTES.get(objective, ""), "checked": CHECKED,
            "disclaimer": "Interfeys va shartlar o'zgarishi mumkin: har qadamni rasmiy yordam sahifasi bilan solishtiring."}
