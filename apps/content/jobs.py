from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.jobs.queue import JobContext, register_handler

from . import temphost
from .models import TempObject
from .services import publish_target


@register_handler("publish_item", "publish")
def publish_item(ctx: JobContext):
    return publish_target(ctx.payload["content_item_id"], ctx.payload["target_id"])


@register_handler("r2_cleanup", "system")
def r2_cleanup(ctx: JobContext):
    """Tugagan nashrlar fayllarini, eskirgan va yetim obyektlarni o'chiradi."""
    now = timezone.now()
    n = 0
    keep = timedelta(hours=int(get_setting("publish.r2.keep_failed_hours", 24)))
    manual = temphost.retention_manual() and not settings.USE_FAKES
    for o in TempObject.objects.filter(status="uploaded"):
        item = o.item
        expired = o.delete_after and o.delete_after < now
        if manual:
            if expired and o.backend == "worker_kv":   # KV'da muddat tugagach fayl o'zi yo'qoladi — yozuvni yangilaymiz
                o.status = "deleted"
                o.save(update_fields=["status"])
                n += 1
            continue
        done = item is None or not item.targets.exclude(status__in=["published"]).exists()
        failed_old = o.created_at < now - keep
        if done or failed_old or expired:
            temphost.delete_object(o, fake=settings.USE_FAKES)
            n += 1
    orphans = 0
    if not settings.USE_FAKES and get_setting("r2.bucket") and get_setting("cloud.sweep_orphans", False):
        try:
            known = set(TempObject.objects.filter(backend="r2", status="uploaded").values_list("key", flat=True))
            host = temphost.R2Host()
            for k in host.list_keys():
                if k not in known:
                    host.delete(k)
                    orphans += 1
        except Exception:  # noqa: BLE001
            pass
    return {"deleted": n, "orphans": orphans}


@register_handler("cloud_upload", "media")
def cloud_upload(ctx: JobContext):
    """Saqlangan media faylni Cloudflare'ga yuklaydi (katta fayllar navbatda, holati menyuda ko'rinadi)."""
    o = TempObject.objects.filter(pk=ctx.payload["temp_id"]).select_related("asset", "item").first()
    if o is None or o.status not in ("pending", "failed"):
        return {"skipped": True}
    o = temphost.upload_pending(o, fake=settings.USE_FAKES)
    return {"status": o.status}


@register_handler("trash_purge", "system")
def trash_purge(ctx: JobContext):
    from .models import ContentItem
    old = ContentItem.all_objects.filter(deleted_at__lt=timezone.now() - timedelta(days=30))
    n = old.count()
    old.delete()
    return {"purged": n}


@register_handler("activity_digest", "system")
def activity_digest(ctx: JobContext):
    """Har kuni ertalab: kecha kim nima qildi — adminlarga (Telegram + bildirishnoma)."""
    from datetime import timedelta as _td
    from apps.accounts.models import User
    from apps.core.models import Notification
    from apps.core.utils import local
    from apps.jobs.queue import enqueue
    from apps.web.views_activity import build_digest
    day = (local(timezone.now()) - _td(days=1)).date()
    text = build_digest(day)
    n = 0
    for u in User.objects.filter(is_active=True, is_admin=True):
        note = Notification.objects.create(user=u, type="activity.digest", severity="info", title=f"Kunlik xulosa — {day:%d.%m.%Y}", body=text, link="/faoliyat/",
                                           dedupe_key=f"digest:{day}:{u.pk}")
        if getattr(u, "telegram_id", None):
            enqueue("notify_telegram", {"notification_id": note.pk}, queue="system")
        n += 1
    return {"sent": n}
