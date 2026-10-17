"""Bildirishnomalar: dedupe, foydalanuvchi sozlamasi, Telegram (ixtiyoriy)."""
from datetime import timedelta

from django.utils import timezone

from .models import Notification, NotificationPref
from .settings_store import get_setting

TYPES = {
    "stories.result": "Story natijasi", "stories.account": "Story akkaunti",
    "inbox.new": "Yangi murojaat", "inbox.handoff": "Operator kerak",
    "task.assigned": "Yangi vazifa", "approval.requested": "Tasdiqlash so'rovi",
    "content.status_changed": "Kontent holati o'zgardi", "publish.success": "Nashr muvaffaqiyatli",
    "publish.failed": "Nashr xatosi", "publish.missed_window": "Nashr vaqti o'tib ketdi",
    "quota.warning": "Kvota ogohlantirishi", "quota.exhausted": "Kvota tugadi",
    "token.expiring": "Token tugayapti", "anomaly.detected": "Anomaliya",
    "report.ready": "Hisobot tayyor",
    "provider.switched": "Provayder almashdi", "r2.full": "R2 to'lgan",
    "job.failed": "Vazifa xatosi", "activity.digest": "Kunlik xulosa", "content.ready": "Kontent tayyor", "competitor.hit": "Raqobatchi posti yaxshi chiqdi", "alert.smart": "Aqlli ogohlantirish", "idea.new": "Yangi g'oya", "design.status": "Dizayner vazifasi", "post.insight": "Post natijasi xulosasi", "connection.error": "Ulanish xatosi", "client.issue": "Mijoz xabari", "goal.behind": "Maqsad ortda qolmoqda", "goal.achieved": "Maqsadga erishildi", "goal.missed": "Maqsad muddati tugadi",
}


def notify(type_: str, title: str, body: str = "", *, business_id: int | None = None,
           severity: str = "info", link: str = "", dedupe_key: str = "", users=None, dedupe_minutes: int | None = None) -> int:
    """Kerakli foydalanuvchilarga bildirishnoma yaratadi. Qaytaradi: yaratilganlar soni."""
    from apps.accounts.models import User
    from apps.accounts.services import PermissionService

    since = timezone.now() - timedelta(minutes=int(dedupe_minutes if dedupe_minutes is not None else get_setting("notify.dedupe_minutes", 30)))
    if dedupe_key and Notification.objects.filter(dedupe_key=dedupe_key, created_at__gte=since).exists():
        return 0
    if users is None:
        ps = PermissionService()
        users = [u for u in User.objects.filter(is_active=True)
                 if u.is_admin or (business_id and ps.can(u, "notifications.view",
                                                          _biz(business_id)))]
    mandatory = set(get_setting("notify.mandatory", []))
    n = 0
    for u in users:
        pref = NotificationPref.objects.filter(user=u, type=type_).first()
        if pref and not pref.web and type_ not in mandatory:
            continue
        note = Notification.objects.create(user=u, business_id=business_id, type=type_, severity=severity,
                                           title=title[:200], body=body, link=link, dedupe_key=dedupe_key)
        n += 1
        if getattr(u, "telegram_id", None) and (type_ in mandatory or (pref and pref.telegram)):
            from apps.jobs.queue import enqueue
            enqueue("notify_telegram", {"notification_id": note.pk}, queue="system")
    return n


def _biz(bid):
    from apps.businesses.models import Business
    return Business.objects.filter(pk=bid).first()
