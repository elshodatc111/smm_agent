"""Standart bot oqimi, matnlar va ularni tekshirish/tozalash. Barcha matn faqat o'zbek tilida."""
from __future__ import annotations

import copy
import re

ACTIONS = [
    ("screen", "Boshqa ekranni ochish"), ("url", "Havola ochish"), ("tariffs", "Tariflar va to'lov"),
    ("status", "Obuna holatim"), ("join", "Guruhga kirish havolasi"), ("ai", "AI mentor"), ("stat", "Statistika (faqat adminlar)"),
]
ACTION_KEYS = [a for a, _ in ACTIONS]
PLACEHOLDERS = ["name", "bot", "tariff", "price", "days", "card", "holder", "bank", "end", "left", "reason", "project"]

# Tizim ekranlari (o'chirib bo'lmaydi)
CORE_SCREENS = ["start", "phone", "menu"]

DEFAULT_TEXTS = {
    "tariffs_title": "💎 Tarifni tanlang:",
    "no_tariffs": "Hozircha tariflar tayyor emas. Keyinroq urinib ko'ring.",
    "pay_info": ("💳 <b>To'lov</b>\n\nTarif: <b>{tariff}</b>\nSumma: <b>{price} so'm</b>\nMuddat: {days} kun\n\n"
                 "Karta: <code>{card}</code>\nEgasi: {holder}\nBank: {bank}\n\n"
                 "To'lovni amalga oshirgach, <b>chek rasmini</b> (skrinshot) shu yerga yuboring."),
    "pay_no_card": "To'lov rekvizitlari hali kiritilmagan. Iltimos, keyinroq urinib ko'ring.",
    "pay_wait": "✅ Chek qabul qilindi. Mas'ul shaxs tekshirmoqda, tez orada javob beramiz.",
    "need_photo": "Iltimos, to'lov chekining <b>rasmini</b> yuboring (skrinshot).",
    "approved": "🎉 To'lov tasdiqlandi! Obunangiz <b>{end}</b> gacha faol.\nGuruhga kirish uchun quyidagi havolalarni bosing 👇",
    "rejected": "❌ To'lovingiz tasdiqlanmadi.\nSabab: {reason}\n\nSavolingiz bo'lsa, qayta urinib ko'ring: /start",
    "expiring": "⏰ Obunangiz <b>{left} kundan</b> keyin ({end}) tugaydi. Davom etish uchun /start bosing va tarifni tanlang.",
    "expired": "Obuna muddatingiz tugadi va guruhdan chiqarildingiz. Qayta obuna bo'lish uchun /start bosing.",
    "no_sub": "Sizda faol obuna yo'q. Obuna bo'lish uchun «Tariflar» tugmasini bosing.",
    "status_active": "✅ Obunangiz faol.\nTugash sanasi: <b>{end}</b> ({left} kun qoldi).",
    "join_links": "Guruhga kirish havolalari 👇 (so'rov yuborganingizda avtomatik qabul qilinasiz):",
    "no_groups": "Guruh hali ulanmagan. Iltimos, mas'ul shaxsga murojaat qiling.",
    "join_denied": "Guruhga kirish uchun faol obuna kerak. Botga o'ting va tarifni tanlang: /start",
    "phone_thanks": "Rahmat! Raqamingiz qabul qilindi ✅",
    "phone_bad": "Iltimos, pastdagi tugma orqali <b>o'z raqamingizni</b> yuboring.",
    "ai_intro": "🤖 AI mentor ulandi. Savolingizni yozing. Chiqish uchun /menu bosing.",
    "ai_limit": "Bugungi bepul savollar limiti tugadi ({limit} ta). Cheklovsiz foydalanish uchun obuna bo'ling: /start",
    "ai_off": "AI mentor hozircha o'chirilgan.",
    "ai_error": "AI hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring.",
    "blocked": "Kechirasiz, siz bilan ishlay olmaymiz.",
    "stat_denied": "Bu bo'lim faqat mas'ul adminlar uchun.",
    "unknown": "Tushunmadim. Bosh menyu uchun /menu bosing.",
}

DEFAULT_SCREENS = {
    "start": {"title": "Salom ekrani", "text": "Assalomu alaykum, <b>{name}</b>! 👋\n\n<b>{project}</b> botiga xush kelibsiz.\nBu yerda tarifni tanlab, yopiq guruhga obuna bo'lishingiz va AI mentordan yordam olishingiz mumkin.",
              "media": None, "rows": []},
    "phone": {"title": "Telefon so'rash", "text": "Davom etish uchun telefon raqamingizni yuboring 👇\n(Pastdagi «Raqamni yuborish» tugmasini bosing.)",
              "media": None, "rows": [], "btn": "📱 Raqamni yuborish"},
    "menu": {"title": "Bosh menyu", "text": "Bosh menyu. Kerakli bo'limni tanlang 👇", "media": None,
             "rows": [[{"t": "💎 Tariflar", "a": "tariffs"}], [{"t": "🤖 AI mentor", "a": "ai"}, {"t": "📊 Obuna holatim", "a": "status"}],
                      [{"t": "🔗 Guruhga kirish", "a": "join"}]]},
}


def default_flow() -> dict:
    return {"screens": copy.deepcopy(DEFAULT_SCREENS), "texts": copy.deepcopy(DEFAULT_TEXTS)}


def get_flow(project, draft: bool = False) -> dict:
    """Saqlangan oqim + yetishmayotgan joylar standart bilan to'ldiriladi."""
    raw = copy.deepcopy((project.flow_draft if draft and project.flow_draft else project.flow) or {})
    base = default_flow()
    screens = {**base["screens"], **(raw.get("screens") or {})}
    texts = {**base["texts"], **(raw.get("texts") or {})}
    for k, s in screens.items():
        s.setdefault("title", k)
        s.setdefault("text", "")
        s.setdefault("media", None)
        s.setdefault("rows", [])
    return {"screens": screens, "texts": texts}


_KEY = re.compile(r"^[a-z0-9_]{1,24}$")


def clean_flow(data: dict, media_ids: set[int] | None = None) -> tuple[dict, list[str]]:
    """Paneldan kelgan oqimni tozalaydi; (toza oqim, ogohlantirishlar). Xato bo'lsa ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Oqim formati noto'g'ri.")
    scr_in = data.get("screens") or {}
    txt_in = data.get("texts") or {}
    if not isinstance(scr_in, dict) or not isinstance(txt_in, dict):
        raise ValueError("Oqim formati noto'g'ri.")
    if len(scr_in) > 40:
        raise ValueError("Ekranlar soni 40 tadan oshmasligi kerak.")
    screens, warns = {}, []
    for k, s in scr_in.items():
        if not _KEY.match(str(k)) or not isinstance(s, dict):
            raise ValueError(f"Ekran kaliti noto'g'ri: «{k}» (faqat kichik lotin harf, raqam va _).")
        text = str(s.get("text", ""))[:3500]
        media = s.get("media")
        media = int(media) if isinstance(media, (int, str)) and str(media).isdigit() and (media_ids is None or int(media) in media_ids) else None
        rows = []
        for row in (s.get("rows") or [])[:8]:
            r = []
            for b in (row or [])[:3]:
                t = str(b.get("t", "")).strip()[:40]
                a = b.get("a") if b.get("a") in ACTION_KEYS else "screen"
                v = str(b.get("v", "")).strip()[:300]
                if not t:
                    continue
                r.append({"t": t, "a": a, "v": v})
            if r:
                rows.append(r)
        scr = {"title": str(s.get("title") or k)[:60], "text": text, "media": media, "rows": rows}
        if k == "phone":
            scr["btn"] = str(s.get("btn") or "📱 Raqamni yuborish")[:40]
        screens[k] = scr
    for k in CORE_SCREENS:
        if k not in screens:
            raise ValueError(f"«{k}» ekrani o'chirilmasligi kerak.")
    for k, s in screens.items():
        if not s["text"].strip() and not s["media"]:
            warns.append(f"«{s['title']}» ekranida matn ham, media ham yo'q.")
        for row in s["rows"]:
            for b in row:
                if b["a"] == "screen" and b["v"] not in screens:
                    warns.append(f"«{s['title']}» ekranidagi «{b['t']}» tugmasi mavjud bo'lmagan ekranga olib boradi.")
                if b["a"] == "url" and not re.match(r"^(https?://|tg://|t\.me/)", b["v"]):
                    warns.append(f"«{s['title']}»: «{b['t']}» havolasi http(s):// bilan boshlanishi kerak.")
    texts = {k: str(txt_in.get(k, v))[:3500] for k, v in DEFAULT_TEXTS.items()}
    return {"screens": screens, "texts": texts}, warns


def fmt(text: str, **vals) -> str:
    """{name} kabi joylarni almashtiradi (noma'lum joylar o'zgarishsiz qoladi; boshqa { } xavfsiz)."""
    def rep(m):
        k = m.group(1)
        return str(vals[k]) if k in vals and vals[k] is not None else m.group(0)
    return re.sub(r"\{(\w+)\}", rep, text or "")


def money(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def card_fmt(c: str) -> str:
    d = re.sub(r"\D", "", c or "")
    return " ".join(d[i:i + 4] for i in range(0, len(d), 4)) if d else (c or "")


def markup_for(rows: list, is_admin: bool = False) -> dict | None:
    """Oqim qatorlaridan Telegram inline klaviatura."""
    out = []
    for row in rows or []:
        r = []
        for b in row:
            a, v, t = b["a"], b.get("v", ""), b["t"]
            if a == "url":
                u = v if v.startswith(("http", "tg://")) else "https://" + v
                r.append({"text": t, "url": u})
            elif a == "screen":
                r.append({"text": t, "callback_data": f"s:{v}"[:64]})
            elif a == "stat" and not is_admin:
                continue
            else:
                r.append({"text": t, "callback_data": a})
        if r:
            out.append(r)
    return {"inline_keyboard": out} if out else None
