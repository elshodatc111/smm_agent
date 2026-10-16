"""Barcha ruxsat kodlari bitta joyda: <modul>.<amal>."""
MODULES = {
    "dashboard": "Boshqaruv paneli", "businesses": "Bizneslar", "connections": "Ulanishlar",
    "competitors": "Raqobatchilar", "analytics": "Tahlil", "calendar": "Kontent kalendar",
    "publish": "Nashr", "approvals": "Tasdiqlash", "ai_studio": "AI studiya", "scripts": "Ssenariylar",
    "media_analysis": "Media tahlil", "hooks": "Hook bazasi",
    "ads": "Reklama tavsiyalari", "reports": "Hisobotlar",
    "notifications": "Bildirishnomalar", "system_health": "Tizim holati", "settings": "Sozlamalar",
    "users": "Foydalanuvchilar", "guides": "Yo'riqnoma",
    "goals": "Maqsadlar", "inbox": "Murojaatlar",
}
ACTIONS = {
    "view": "Ko'rish", "create": "Yaratish", "edit": "Tahrirlash", "delete": "O'chirish",
    "approve": "Tasdiqlash", "publish": "Nashr qilish", "export": "Eksport", "configure": "Sozlash",
}
# Biznesga bog'lanmagan (global) modullar
GLOBAL_MODULES = {"settings", "users", "system_health", "guides"}
# Keyinroq qo'shilgan modullar: mavjud rollarga bir marta beriladigan standart ruxsatlar (bootstrap)
LATE_MODULES = {
    "goals": {"Menejer": "view,create,edit,delete", "SMM mutaxassis": "view,create,edit", "Targetolog": "view", "Analitik": "view,export", "Kontent-maker": "view"},
    "inbox": {"Menejer": "view,create,edit,configure", "SMM mutaxassis": "view,create,edit"},
}

ALL_CODES = [f"{m}.{a}" for m in MODULES for a in ACTIONS]


def validate(code: str) -> str:
    if code not in ALL_CODES:
        raise ValueError(f"Noma'lum ruxsat kodi: {code}")
    return code


def codes(spec: dict[str, str]) -> set[str]:
    """{'calendar': 'view,create'} -> {'calendar.view', 'calendar.create'}"""
    out = set()
    for mod, acts in spec.items():
        for a in acts.split(","):
            out.add(validate(f"{mod}.{a.strip()}"))
    return out


VIEW_ALL = {m: "view" for m in MODULES if m not in ("settings", "users", "system_health", "inbox")}  # tizim bo'limlari faqat admin / alohida beriladi

PRESET_ROLES = {
    "Menejer": {**VIEW_ALL, "inbox": "view,create,edit,configure", "goals": "view,create,edit,delete", "businesses": "view,create,edit", "connections": "view,create,edit",
                "competitors": "view,create,edit,delete", "analytics": "view,export",
                "calendar": "view,create,edit,delete", "approvals": "view,approve",
                "publish": "view,publish", "ai_studio": "view,create", "scripts": "view,create,edit",
                "hooks": "view,create,edit", "ads": "view,create,edit",
                "reports": "view,create,export", "notifications": "view",
                "media_analysis": "view,create"},
    "SMM mutaxassis": {**VIEW_ALL, "inbox": "view,create,edit", "goals": "view,create,edit", "calendar": "view,create,edit", "competitors": "view",
                       "ai_studio": "view,create", "scripts": "view,create,edit", "hooks": "view,create,edit",
                       "media_analysis": "view,create", "analytics": "view",
                       "notifications": "view"},
    "Targetolog": {**VIEW_ALL, "goals": "view", "ads": "view,create,edit", "analytics": "view,export",
                   "reports": "view,export", "competitors": "view", "notifications": "view"},
    "Kontent-maker": {"dashboard": "view", "calendar": "view,edit", "media_analysis": "view,create",
                      "notifications": "view", "guides": "view"},
    "Analitik": {**VIEW_ALL, "goals": "view,export", "analytics": "view,export", "reports": "view,create,export",
                 "competitors": "view", "notifications": "view"},
}
