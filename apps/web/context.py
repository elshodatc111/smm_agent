from django.urls import reverse

from apps.accounts.services import perms

NAV = [
    ("Asosiy", [("dashboard", "Boshqaruv paneli", "dashboard", "dashboard", "home"),
                ("analytics", "Tahlil", "analytics", "analytics", "chart"),
                ("analytics", "Postlar statistikasi", "post_list", "analytics", "film"),
                ("analytics", "Kunlik statistika", "daily_stats", "analytics", "pulse"),
                ("competitors", "Raqobatchilar", "competitor_list", "competitors", "users")]),
    ("Kontent", [("calendar", "Kontent kalendar", "calendar", "calendar", "cal"),
                 ("calendar", "Vazifalar", "my_tasks", "calendar", "check"),
                 ("ai_studio", "G'oyalar banki", "ideas_home", "ai_studio", "bulb"),
                 ("ai_studio", "AI studiya", "studio_home", "ai_studio", "spark"),
                 ("calendar", "Shablonlar", "template_list", "calendar", "scroll"),
                 ("publish", "Nashr jurnali", "publish_log", "publish", "send"),
                 ("publish", "Fayllar (Cloudflare)", "cloud_home", "publish", "cloud"),
                 ("media_analysis", "Media tahlil", "media_list", "media_analysis", "film"),
                 ("calendar", "Savat", "trash_list", "calendar", "trash")]),
    ("Biznes", [("businesses", "Bizneslar", "business_list", "businesses", "brief"),
                ("connections", "Ulanishlar", "connection_list", "connections", "link"),
                ("ads", "Reklama", "ads_home", "ads", "mega"),
                ("reports", "Hisobotlar", "report_list", "reports", "file"),
                ("links", "Havolalar", "link_list", "links", "tag")]),
    ("Tizim", [("activity", "Faoliyat jurnali", "activity_log", "businesses", "history"),
               ("notifications", "Ogohlantirishlar", "alerts_home", "notifications", "bell"),
               ("system_health", "Tizim holati", "health", "system_health", "pulse"),
               ("users", "Foydalanuvchilar", "user_list", "users", "users"),
               ("settings", "Sozlamalar", "settings_home", "settings", "gear"),
               ("guides", "Yo'riqnoma", "guide_index", "guides", "book")]),
]


def nav_for(request) -> list[dict]:
    """Foydalanuvchi ruxsatiga mos menyu (bo'lim -> elementlar). Ikonka nomlari frontendda ikonkaga aylanadi."""
    user = request.user
    biz = getattr(request, "business", None)
    nav = []
    for sec, items in NAV:
        rows = []
        for key, label, url_name, module, icon in items:
            if user.is_admin:
                ok = True
            elif key == "activity":
                ok = bool(biz and perms.can(user, "businesses.edit", biz)) or (not biz and perms.businesses_for(user, "businesses.edit").exists())
            elif module in ("settings", "users", "system_health", "guides"):
                ok = perms.can(user, f"{module}.view", None)
            else:
                ok = perms.can(user, f"{module}.view", biz) if biz else perms.businesses_for(user, f"{module}.view").exists()
            if ok:
                rows.append({"label": label, "url": reverse(url_name), "icon": icon, "key": key})
        if rows:
            nav.append({"title": sec, "items": rows})
    return nav


def session_payload(request) -> dict:
    """React ilovasi boshlanishida va har o'zgarishdan keyin oladigan umumiy holat."""
    from apps.core.models import Notification
    from apps.web.spa import brand_payload
    user = getattr(request, "user", None)
    out = {"brand": brand_payload(), "authenticated": bool(user and user.is_authenticated)}
    if not out["authenticated"]:
        return out
    biz = getattr(request, "business", None)
    out.update(
        user={"id": user.pk, "username": user.username, "name": user.display(), "is_admin": user.is_admin, "theme": user.theme},
        nav=nav_for(request),
        businesses=[{"id": b.pk, "name": b.name} for b in perms.businesses_for(user)],
        business={"id": biz.pk, "name": biz.name} if biz else None,
        unread=Notification.objects.filter(user=user, read_at__isnull=True).count(),
    )
    return out
