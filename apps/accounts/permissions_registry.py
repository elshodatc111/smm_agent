"""Ruxsatlar katalogi: har bir bo'lim uchun FAQAT kodda haqiqatan tekshiriladigan amallar.

Kod ko'rinishi: <modul>.<amal>. Admin barcha narsani qila oladi. «Faqat admin» belgilangan ruxsatlar boshqa foydalanuvchiga
umuman berilmaydi (rol, individual ruxsat bo'lsa ham ishlamaydi)."""

# guruh -> menyudagi tartib ham shu
GROUPS = [("main", "Bosh"), ("clients", "Mijozlar"), ("content", "Kontent"), ("publish", "Nashr"), ("online", "Onlayn kanal"), ("analysis", "Tahlil"), ("system", "Tizim")]

# modul: (nomi, guruh, global?, {amal: (nomi, tavsifi, faqat_admin?)})
_C = {
    "dashboard": ("Boshqaruv paneli", "main", False, {"view": ("Ko'rish", "Umumiy ko'rsatkichlar paneli", False)}),
    "notifications": ("Ogohlantirishlar", "main", False, {"view": ("Ko'rish", "Bildirishnomalar va aqlli ogohlantirishlarni ko'rish", False)}),
    "businesses": ("Bizneslar", "clients", False, {
        "view": ("Ko'rish", "Biznes ro'yxati va kartochkasi", False),
        "edit": ("Tahrirlash", "Biznes ma'lumoti, faktlar, brend xotirasi, logotip", False),
        "create": ("Yangi biznes qo'shish", "Faqat admin", True), "delete": ("Biznesni o'chirish", "Faqat admin", True)}),
    "inbox": ("Murojaatlar", "clients", False, {
        "view": ("Ko'rish", "Suhbatlar va murojaatlar jurnalini ko'rish", False),
        "create": ("Javob yozish", "Mijozga operator sifatida javob yozish, suhbatni yopish", False),
        "edit": ("AI skripti va suhbat boshqaruvi", "Skript yozuvlarini qo'shish/tahrirlash, AI ni yoqish/o'chirish", False),
        "configure": ("Akkaunt ulash va sozlash", "Faqat admin", True)}),
    "goals": ("Maqsadlar", "clients", False, {
        "view": ("Ko'rish", "Maqsadlar va ularning borishi", False), "create": ("Yaratish", "Yangi maqsad qo'yish", False), "edit": ("Tahrirlash", "Maqsadni o'zgartirish/yopish", False)}),
    "connections": ("Ulanishlar", "clients", False, {
        "view": ("Ko'rish", "Ulangan akkauntlar holatini ko'rish", False),
        "create": ("Yangi akkaunt ulash", "Faqat admin", True), "edit": ("Ulanishni boshqarish", "Faqat admin", True), "delete": ("Ulanishni o'chirish", "Faqat admin", True)}),
    "calendar": ("Kontent kalendar", "content", False, {
        "view": ("Ko'rish", "Kalendar, postlar, vazifalar, shablonlar, savat", False),
        "create": ("Post yaratish", "Yangi post/qoralama yaratish, fayl yuklash", False),
        "edit": ("Tahrirlash", "Post matni, vaqti, fayllarini o'zgartirish; vazifalarni bajarish", False),
        "delete": ("O'chirish", "Postni savatga tashlash va savatni tozalash", False)}),
    "ai_studio": ("AI studiya", "content", False, {
        "view": ("Ko'rish", "Kontent reja, karusel ssenariy, g'oyalar banki, AI takliflar", False),
        "create": ("AI bilan yaratish", "Reja, karusel, g'oya va ssenariy yaratish", False)}),
    "scripts": ("Ssenariylar", "content", False, {
        "view": ("Ko'rish", "Ssenariylar ro'yxati", False), "create": ("Yaratish", "Yangi ssenariy", False), "edit": ("Tahrirlash", "Ssenariyni tahlil qilish/o'zgartirish", False)}),
    "hooks": ("Hook bazasi", "content", False, {"edit": ("Yangilash", "G'olib postlardan hooklar olish", False)}),
    "media_analysis": ("Media tahlil", "content", False, {
        "view": ("Ko'rish", "Media tahlil natijalari", False), "create": ("Tahlil qilish", "Video/rasmni tahlilga yuborish", False)}),
    "publish": ("Nashr", "publish", False, {
        "view": ("Ko'rish", "Nashr jurnali va Cloudflare saqlash", False),
        "publish": ("Nashr qilish", "Postni hozir nashr qilish, qayta urinish, to'xtatish", False)}),
    "stories": ("Telegram Stories", "publish", True, {
        "view": ("Ko'rish", "Storylar, kalendar, statistika", False),
        "create": ("Story yuklash", "Yangi story yaratish va rejalashtirish", False),
        "edit": ("Boshqarish", "Kutilayotganlarni to'xtatish, xatolarni qayta urinish", False),
        "configure": ("Akkaunt ulash va o'chirish", "Faqat admin", True)}),
    "online": ("Onlayn kanal", "online", True, {
        "view": ("Ko'rish", "Loyihalar, statistika, obunachilar va to'lovlar ro'yxati", False),
        "leads_view": ("Leadlarni ko'rish", "Leadlar ro'yxati va kartochkasi (telefon raqamlari bilan)", False),
        "leads_edit": ("Leadlar bilan ishlash", "Holat, izoh, biriktirish, qora ro'yxat", False),
        "export": ("Excelga yuklab olish", "Leadlar va to'lovlar eksporti", False),
        "payments": ("To'lovlarni tasdiqlash", "Paneldan to'lovni tasdiqlash yoki rad etish", False),
        "members": ("Obunani boshqarish", "Qo'lda obuna berish, uzaytirish, bekor qilish, guruhdan chiqarish", False),
        "edit": ("Bot, tarif va AI mentorni tahrirlash", "Bot oqimi (tugma/javoblar), tariflar, bilim bazasi, AI sozlamasi", False),
        "publish": ("Botni joriy qilish", "Qoralamani joriy qilish, botni Telegramda sozlash", False),
        "configure": ("Loyiha, token, karta va guruhlar", "Faqat admin", True)}),
    "analytics": ("Tahlil", "analysis", False, {"view": ("Ko'rish", "Tahlil, kunlik statistika, post natijalari", False)}),
    "competitors": ("Raqobatchilar", "analysis", False, {
        "view": ("Ko'rish", "Raqobatchilar ro'yxati va tahlili", False), "create": ("Qo'shish", "Yangi raqobatchi", False),
        "edit": ("Tahrirlash", "Raqobatchi ma'lumoti", False), "delete": ("O'chirish", "Raqobatchini olib tashlash", False)}),
    "ads": ("Reklama tahlili", "analysis", False, {
        "view": ("Ko'rish", "Reklama tavsiyalari", False), "create": ("Yaratish", "Yangi reklama tavsiyasi", False), "edit": ("Tahrirlash", "Tavsiyani o'zgartirish", False)}),
    "reports": ("Hisobotlar", "analysis", False, {
        "view": ("Ko'rish", "Hisobotlarni ko'rish", False), "create": ("Yaratish", "Yangi hisobot va jadval", False), "export": ("Yuklab olish / ulashish", "Excel va ochiq havola", False)}),
    "guides": ("Yo'riqnoma", "system", True, {"view": ("Ko'rish", "Yo'riqnomalar", False)}),
    "settings": ("Sozlamalar", "system", True, {"view": ("Ko'rish", "Faqat admin", True), "configure": ("O'zgartirish", "Faqat admin", True)}),
    "users": ("Foydalanuvchilar va rollar", "system", True, {a: (a, "Faqat admin", True) for a in ("view", "create", "edit", "delete")}),
    "system_health": ("Tizim holati", "system", True, {"view": ("Ko'rish", "Faqat admin", True), "configure": ("Boshqarish", "Faqat admin", True)}),
}
CATALOG = {m: {"label": v[0], "group": v[1], "global": v[2], "actions": {a: {"label": x[0], "help": x[1], "admin": x[2]} for a, x in v[3].items()}} for m, v in _C.items()}

MODULES = {m: c["label"] for m, c in CATALOG.items()}
ACTIONS = {"view": "Ko'rish", "create": "Yaratish", "edit": "Tahrirlash", "delete": "O'chirish", "publish": "Nashr", "export": "Eksport", "configure": "Sozlash"}
GLOBAL_MODULES = {m for m, c in CATALOG.items() if c["global"]}
ALL_CODES = [f"{m}.{a}" for m, c in CATALOG.items() for a in c["actions"]]
ADMIN_ONLY = {f"{m}.{a}" for m, c in CATALOG.items() for a, x in c["actions"].items() if x["admin"]}
GRANTABLE = [c for c in ALL_CODES if c not in ADMIN_ONLY]


def grantable_groups():
    """Admin interfeysi uchun: [(guruh nomi, [(modul, nomi, [(kod, nomi, tavsif)])])] — faqat berilishi mumkin bo'lganlar."""
    out = []
    for gk, gname in GROUPS:
        mods = []
        for m, c in CATALOG.items():
            if c["group"] != gk:
                continue
            acts = [(f"{m}.{a}", x["label"], x["help"]) for a, x in c["actions"].items() if not x["admin"]]
            if acts:
                mods.append((m, c["label"], acts))
        if mods:
            out.append((gname, mods))
    return out


# Keyinroq qo'shilgan modullar: mavjud rollarga bir marta beriladigan standart ruxsatlar (bootstrap)
LATE_MODULES = {
    "goals": {"Menejer": "view,create,edit", "SMM mutaxassis": "view,create,edit", "Targetolog": "view", "Analitik": "view", "Kontent-maker": "view"},
    "inbox": {"Menejer": "view,create,edit", "SMM mutaxassis": "view,create,edit"},
    "stories": {"Menejer": "view,create,edit", "SMM mutaxassis": "view,create,edit"},
}


def validate(code: str) -> str:
    if code not in ALL_CODES:
        raise ValueError(f"Noma'lum ruxsat kodi: {code}")
    return code


def codes(spec: dict[str, str]) -> set[str]:
    """{'calendar': 'view,create'} -> {'calendar.view', 'calendar.create'}; faqat admin kodlari tashlab ketiladi."""
    out = set()
    for mod, acts in spec.items():
        for a in acts.split(","):
            c = validate(f"{mod}.{a.strip()}")
            if c not in ADMIN_ONLY:
                out.add(c)
    return out


def _all_view(skip=()):
    return {m: "view" for m, c in CATALOG.items() if "view" in c["actions"] and f"{m}.view" not in ADMIN_ONLY and m not in skip}


VIEW_ALL = _all_view(skip=("stories", "inbox", "online"))

# Tayyor andozalar (admin xohlagancha o'zgartiradi yoki har xodimga alohida ruxsat beradi)
PRESET_ROLES = {
    "Menejer": {**VIEW_ALL, "businesses": "view,edit", "inbox": "view,create,edit", "goals": "view,create,edit", "calendar": "view,create,edit,delete",
                "publish": "view,publish", "ai_studio": "view,create", "scripts": "view,create,edit", "hooks": "edit", "ads": "view,create,edit",
                "competitors": "view,create,edit,delete", "reports": "view,create,export", "media_analysis": "view,create", "stories": "view,create,edit"},
    "SMM mutaxassis": {**VIEW_ALL, "inbox": "view,create,edit", "goals": "view,create,edit", "calendar": "view,create,edit", "ai_studio": "view,create",
                       "scripts": "view,create,edit", "hooks": "edit", "media_analysis": "view,create", "stories": "view,create,edit"},
    "Targetolog": {**VIEW_ALL, "ads": "view,create,edit", "reports": "view,export", "competitors": "view"},
    "Kontent-maker": {"dashboard": "view", "calendar": "view,edit", "media_analysis": "view,create", "notifications": "view", "guides": "view"},
    "Analitik": {**VIEW_ALL, "reports": "view,create,export", "competitors": "view"},
}
