from django.urls import reverse

from apps.accounts.permissions_registry import GLOBAL_MODULES
from apps.accounts.services import perms
from apps.core.settings_store import get_setting

ICONS = {
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "brief": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2"/>',
    "link": '<path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3.1-6 7-6s7 2.5 7 6"/><path d="M17 4.5a3.5 3.5 0 010 7M22 20c0-2.6-1.7-4.6-4-5.5"/>',
    "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 10h18"/>',
    "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "mega": '<path d="M3 11v2a1 1 0 001 1h2l5 4V6L6 10H4a1 1 0 00-1 1z"/><path d="M15 9a4 4 0 010 6M18 6a8 8 0 010 12"/>',
    "file": '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "pulse": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    "book": '<path d="M4 4h10a4 4 0 014 4v12H8a4 4 0 01-4-4z"/><path d="M4 16a4 4 0 014-4h10"/>',
    "bell": '<path d="M6 8a6 6 0 0112 0c0 7 3 8 3 8H3s3-1 3-8z"/><path d="M10 21a2 2 0 004 0"/>',
    "scroll": '<path d="M8 21h10a2 2 0 002-2V5a2 2 0 00-2-2H8"/><path d="M8 21a2 2 0 01-2-2v-2h4v2a2 2 0 01-2 2zM6 17V5a2 2 0 00-2-2"/>',
    "send": '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
    "cloud": '<path d="M7 18a4 4 0 010-8 5.5 5.5 0 0110.6 1.2A3.4 3.4 0 0117 18z"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "bulb": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0012 3z"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="11" r="2.2"/><path d="M5.5 16.5c.6-1.7 2-2.5 3.5-2.5s2.9.8 3.5 2.5M15 10h4M15 14h3"/>',
    "tag": '<path d="M20 12l-8 8-9-9V3h8z"/><circle cx="7.5" cy="7.5" r="1.2"/>',
}

NAV = [
    ("Bosh", [("dashboard", "Boshqaruv paneli", "dashboard", "dashboard", "home"),
              ("notifications", "Aqlli ogohlantirishlar", "alerts_home", "notifications", "bell")]),
    ("Mijozlar", [("businesses", "Bizneslar", "business_list", "businesses", "brief"),
                  ("inbox", "Murojaatlar", "inbox_home", "inbox", "users"),
                  ("goals", "Maqsadlar", "goals_home", "goals", "target"),
                  ("connections", "Ulanishlar", "connection_list", "connections", "link")]),
    ("Kontent", [("calendar", "Kontent kalendar", "calendar", "calendar", "cal"),
                 ("ai_studio", "Kontent reja", "reja_home", "ai_studio", "cal"),
                 ("ai_studio", "Karusel ssenariy", "carousel_home", "ai_studio", "film"),
                 ("ai_studio", "G'oyalar banki", "ideas_home", "ai_studio", "bulb"),
                 ("ai_studio", "AI takliflar", "studio_home", "ai_studio", "spark"),
                 ("calendar", "Shablonlar", "template_list", "calendar", "scroll"),
                 ("calendar", "Vazifalar", "my_tasks", "calendar", "brief"),
                 ("calendar", "Savat", "trash_list", "calendar", "trash")]),
    ("Nashr", [("publish", "Nashr jurnali", "publish_log", "publish", "send"),
               ("stories", "Telegram Stories", "stories_home", "stories", "film"),
               ("publish", "Cloudflare", "cloud_home", "publish", "cloud")]),
    ("Onlayn kanal", [("online", "Onlayn kanal", "online_home", "online", "tag")]),
    ("Tahlil", [("analytics", "Tahlil", "analytics", "analytics", "chart"),
                ("analytics", "Kunlik statistika", "daily_stats", "analytics", "pulse"),
                ("competitors", "Raqobatchilar", "competitor_list", "competitors", "users"),
                ("ads", "Reklama tahlili", "ads_home", "ads", "mega"),
                ("media_analysis", "Media tahlil", "media_list", "media_analysis", "film"),
                ("reports", "Hisobotlar", "report_list", "reports", "file")]),
    ("Tizim", [("users", "Foydalanuvchilar", "user_list", "users", "users"),
               ("settings", "Sozlamalar", "settings_home", "settings", "gear"),
               ("system_health", "Tizim holati", "health", "system_health", "pulse"),
               ("activity", "Faoliyat jurnali", "activity_log", "businesses", "pulse"),
               ("guides", "Yo'riqnoma", "guide_index", "guides", "book")]),
]
CLOSED_BY_DEFAULT = {"Tizim"}


def ui_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"system_name": get_setting("general.system_name", "SMM Platforma"), "brand_color": get_setting("general.brand_color", "#E11D2E"),
                "default_theme": get_setting("general.theme_default", "light")}
    biz = getattr(request, "business", None)
    nav = []
    cur = request.resolver_match.url_name if getattr(request, "resolver_match", None) else ""
    for sec, items in NAV:
        rows = []
        for key, label, url_name, module, icon in items:
            if user.is_admin:
                ok = True
            elif key == "activity":
                ok = False      # faoliyat jurnali: faqat admin
            elif module in GLOBAL_MODULES:
                ok = perms.can(user, f"{module}.view", None)
            else:
                ok = perms.can(user, f"{module}.view", biz) if biz else perms.businesses_for(user, f"{module}.view").exists()
            if ok:
                rows.append({"label": label, "url": reverse(url_name), "name": url_name, "icon": ICONS[icon], "active": cur == url_name or (cur or "").startswith(url_name.split("_")[0] + "_"), "key": key})
        if rows:
            nav.append({"title": sec, "items": rows, "has_active": any(r["active"] for r in rows),
                        "closed": sec in CLOSED_BY_DEFAULT})
    from apps.core.models import Notification
    return {"system_name": get_setting("general.system_name", "SMM Platforma"), "brand_color": get_setting("general.brand_color", "#E11D2E"),
            "default_theme": get_setting("general.theme_default", "light"), "nav": nav, "icons": ICONS,
            "my_businesses": perms.businesses_for(user), "current_business": biz,
            "unread": Notification.objects.filter(user=user, read_at__isnull=True).count(),
            "nav_urls": {r["name"] for sec in nav for r in sec["items"]}}
