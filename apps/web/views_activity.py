"""Faoliyat jurnali: kim, qachon, nima qildi. Menejer/admin uchun; kunlik xulosa Telegram'ga ham boradi."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render

from apps.accounts.decorators import require_permission
from apps.accounts.models import User
from apps.accounts.services import perms
from apps.core.models import AuditLog
from apps.core.utils import tz
from apps.web import ui

ACTION_UZ = {
    "auth.login": "Tizimga kirdi", "auth.failed": "Kirishda xato parol", "auth.lockout": "Kirish bloklandi",
    "content.create": "Yangi kontent yaratdi", "content.edit": "Kontentni tahrirladi", "content.status": "Kontent holatini o'zgartirdi",
    "content.delete": "Kontentni savatga tashladi", "content.restore": "Kontentni savatdan tikladi", "content.purge": "Kontentni butunlay o'chirdi",
    "content.media": "Media biriktirdi", "content.media_delete": "Mediani postdan olib tashladi", "content.media_edit": "Rasmni tahrirladi (kesdi/siljitdi)", "content.autotime": "Vaqtni avtomatik tanladi", "content.ready": "«Tayyor» deb belgiladi", "content.publish_now": "«Hozir nashr» bosdi", "content.rule_override": "Qoida ogohlantirishini qabul qildi",
    "content.ai_reviewed": "AI xulosasini ko'rib chiqdi", "publish.success": "Nashr muvaffaqiyatli", "publish.failed": "Nashr xatosi",
    "cloud.tags": "Fayl teglarini o'zgartirdi", "cloud.upload": "Cloudflare'ga fayl yukladi", "cloud.delete": "Cloudflare'dan fayl o'chirdi", "cloud.delete_many": "Cloudflare'dan bir nechta fayl o'chirdi",
    "ai.text": "AI matn so'radi", "ai.script": "AI ssenariy so'radi", "ai.youtube": "AI YouTube maydonlarini to'ldirdi",
    "competitor.add": "Raqobatchi qo'shdi", "competitor.delete": "Raqobatchini o'chirdi",
    "connection.create": "Akkaunt ulab qo'ydi", "connection.reconnect": "Akkauntni qayta ulagan", "connection.archive": "Akkauntni arxivladi", "connection.killswitch": "Ulanishni to'xtatdi",
    "business.create": "Biznes qo'shdi", "business.edit": "Biznesni tahrirladi", "business.killswitch": "Biznes nashrini to'xtatdi",
    "brand.version": "Brend qo'llanmasini yangiladi", "brand.approved": "Brend qo'llanmasini tasdiqladi",
    "report.create": "Hisobot yaratdi", "report.deliver": "Hisobot yubordi", "report.share": "Hisobot uchun mijoz havolasini yaratdi", "link.create": "Qisqa havola yaratdi", "link.delete": "Havolani o'chirdi",
    "user.create": "Foydalanuvchi qo'shdi", "user.edit": "Foydalanuvchini tahrirladi", "user.access": "Foydalanuvchi kirishini o'zgartirdi", "role.permissions": "Rol huquqlarini o'zgartirdi",
    "content.media_order": "Karusel fayllari tartibini o'zgartirdi", "content.move": "Postni boshqa kunga ko'chirdi", "content.duplicate": "Postdan nusxa oldi",
    "content.comment": "Postga izoh yozdi", "content.task": "Vazifa berdi", "content.design_status": "Vazifa holatini o'zgartirdi",
    "template.create": "Post shabloni saqladi", "template.delete": "Post shablonini o'chirdi", "lead.add": "Lid qo'shdi", "lead.update": "Lid holatini o'zgartirdi",
    "idea.status": "G'oya holatini o'zgartirdi", "idea.to_post": "G'oyadan post yaratdi", "alerts.settings": "Ogohlantirish sozlamasini o'zgartirdi",
    "setting.changed": "Sozlamani o'zgartirdi", "ai_key.add": "AI kalit qo'shdi", "ai_key.delete": "AI kalitni o'chirdi", "telethon.session_added": "Telethon sessiya qo'shdi",
}
QUIET = {"ai.prompt_scrubbed", "auth.failed"}   # shovqin: asosiy ro'yxatda ko'rsatilmaydi


def label(action: str) -> str:
    return ACTION_UZ.get(action, action)


def _detail(a: AuditLog) -> str:
    d = a.detail or {}
    bits = [str(d[k])[:80] for k in ("title", "file", "name", "platform", "url", "kind", "to", "status") if d.get(k)]
    return " · ".join(bits)


def _link(a: AuditLog) -> str:
    t = a.target or ""
    if t.startswith("item:") and t[5:].isdigit():
        return f"/kalendar/{t[5:]}/"
    return ""


def scope_logs(request):
    if request.user.is_admin:
        qs = AuditLog.objects.all()
        if request.business:
            qs = qs.filter(business_id=request.business.pk)
    else:
        ids = [request.business.pk] if request.business else list(perms.businesses_for(request.user, "businesses.edit").values_list("pk", flat=True))
        qs = AuditLog.objects.filter(business_id__in=ids)
    return qs.exclude(action__in=QUIET).select_related("user")


@login_required
@require_permission("businesses.edit")
def activity_log(request):
    qs = scope_logs(request)
    uid, act = request.GET.get("user", ""), request.GET.get("action", "")
    d1, d2 = request.GET.get("from", ""), request.GET.get("to", "")
    if uid.isdigit():
        qs = qs.filter(user_id=int(uid))
    if act:
        qs = qs.filter(action__startswith=act)
    try:
        if d1:
            qs = qs.filter(at__gte=datetime.combine(date.fromisoformat(d1), datetime.min.time(), tzinfo=tz()))
        if d2:
            qs = qs.filter(at__lt=datetime.combine(date.fromisoformat(d2) + timedelta(days=1), datetime.min.time(), tzinfo=tz()))
    except ValueError:
        pass
    page = Paginator(qs.order_by("-at"), 50).get_page(request.GET.get("p"))
    users = User.objects.filter(is_active=True).order_by("username")
    groups = [("content", "Kontent"), ("publish", "Nashr"), ("cloud", "Cloudflare"), ("ai", "AI"), ("connection", "Ulanishlar"), ("business", "Biznes"),
              ("report", "Hisobot"), ("link", "Havolalar"), ("user", "Foydalanuvchilar"), ("setting", "Sozlamalar"), ("auth", "Kirish")]
    ctx = {"title": "Faoliyat jurnali", "users": users, "groups": groups, "f": {"user": uid, "action": act, "from": d1, "to": d2},
           "rows": [{"at": ui.dt(a.at), "who": (a.user.get_full_name() or a.user.username) if a.user else "Tizim", "what": label(a.action),
                     "detail": _detail(a), "link": _link(a), "biz": a.business_id} for a in page],
           "page": page}
    return render(request, "activity.html", ctx)


def history_for_item(item) -> list[dict]:
    """Bitta post tarixi: xodim harakatlari + nashr urinishlari (vaqt bo'yicha)."""
    from apps.content.models import PublishAttempt
    out = [{"at": a.at, "who": (a.user.get_full_name() or a.user.username) if a.user else "Tizim", "what": label(a.action), "detail": _detail(a)}
           for a in AuditLog.objects.filter(target=f"item:{item.pk}").exclude(action__in=QUIET).select_related("user")]
    for p in PublishAttempt.objects.filter(target__item=item).select_related("target__account"):
        out.append({"at": p.started_at, "who": "Tizim", "what": f"Nashr urinishi #{p.number}: {p.target.account} — {'muvaffaqiyatli' if p.status == 'success' else 'xato'}",
                    "detail": (p.error or "")[:120]})
    out.sort(key=lambda r: r["at"], reverse=True)
    for r in out:
        r["at"] = ui.dt(r["at"])
    return out[:60]


def build_digest(day: date) -> str:
    """Kunlik xulosa matni: «kecha kim nima qildi» (xodim bo'yicha guruhlangan)."""
    from collections import Counter, defaultdict
    a = datetime.combine(day, datetime.min.time(), tzinfo=tz())
    qs = AuditLog.objects.filter(at__gte=a, at__lt=a + timedelta(days=1)).exclude(action__in=QUIET | {"auth.login", "ai.text", "ai.script", "ai.youtube"}).select_related("user")
    by = defaultdict(Counter)
    for x in qs:
        by[(x.user.get_full_name() or x.user.username) if x.user else "Tizim"][label(x.action)] += 1
    if not by:
        return f"📋 {day:%d.%m.%Y}: hech qanday xodim faoliyati qayd etilmadi."
    lines = [f"📋 Kunlik xulosa — {day:%d.%m.%Y}"]
    for who, c in sorted(by.items(), key=lambda kv: -sum(kv[1].values())):
        lines.append(f"\n👤 {who} ({sum(c.values())}):")
        lines += [f"  • {k} — {v} marta" if v > 1 else f"  • {k}" for k, v in c.most_common(8)]
    return "\n".join(lines)
