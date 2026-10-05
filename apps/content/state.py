"""Kontent holat mashinasi. Tasdiqlash bosqichi yo'q: qoralama -> rejalashtirilgan -> nashr."""
from __future__ import annotations

from django.db import transaction

from apps.core.audit import audit
from apps.core.notify import notify

from .models import ContentItem

TRANSITIONS = {
    ("draft", "scheduled"): "calendar.edit",
    ("scheduled", "draft"): "calendar.edit",
    ("scheduled", "publishing"): None,   # faqat worker
    ("publishing", "published"): None,
    ("publishing", "failed"): None,
    ("failed", "scheduled"): "publish.publish",
    ("failed", "draft"): "calendar.edit",
    ("published", "failed"): None,
}


class InvalidTransition(Exception):
    code = "invalid_state_transition"


class NotAllowed(Exception):
    code = "permission_denied"


def can_transition(item: ContentItem, new: str, user=None) -> bool:
    from apps.accounts.services import perms
    perm = TRANSITIONS.get((item.status, new), "__none__")
    if perm == "__none__":
        return False
    if perm is None:
        return user is None  # faqat tizim (worker)
    return user is not None and perms.can(user, perm, item.business)


@transaction.atomic
def transition(item: ContentItem, new: str, user=None, *, note: str = "") -> ContentItem:
    if (item.status, new) not in TRANSITIONS:
        raise InvalidTransition(f"{item.status} -> {new} mumkin emas")
    if not can_transition(item, new, user):
        raise NotAllowed(f"{item.status} -> {new} uchun ruxsat yo'q")
    old = item.status
    if new == "scheduled" and not item.scheduled_at:
        raise InvalidTransition("Rejalashtirish uchun vaqt kerak")
    if new == "scheduled":
        from .services import ensure_ready_to_schedule
        ensure_ready_to_schedule(item)
    item.status = new
    item.save()
    audit("content.status", user=user, business_id=item.business_id, target=f"item:{item.pk}", detail={"from": old, "to": new, "note": note})
    if new in ("published", "failed"):
        notify("content.status_changed", f"{item.title}: {item.get_status_display()}", business_id=item.business_id, link=f"/kalendar/{item.pk}/")
    return item


def auto_schedule(item: ContentItem, user=None) -> str:
    """Saqlangandan keyin: vaqt va maqsad bo'lsa avtomatik rejalashtiradi, aks holda qoralama.
    Qaytaradi: '' (o'zgarmadi) | 'scheduled' | 'draft' | xato matni (rejalashtirib bo'lmadi)."""
    from .services import NotReady
    if item.status in ("publishing", "published"):
        return ""
    if item.status == "scheduled" and not item.scheduled_at:
        transition(item, "draft", user, note="vaqt olib tashlandi")
        return "draft"
    if item.status in ("draft", "failed") and item.scheduled_at and item.targets.exists():
        try:
            transition(item, "scheduled", user, note="avto-rejalashtirish")
            return "scheduled"
        except NotReady as e:
            return str(e)
        except (InvalidTransition, NotAllowed) as e:
            return str(e)
    return ""


def on_item_edited(item: ContentItem, user=None) -> str:
    """Tahrirdan keyin qayta tekshiradi (tasdiq talab qilinmaydi)."""
    return auto_schedule(item, user)
