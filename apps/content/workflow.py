"""Dizayner/kontent-maker ish oqimi: vazifa, muddat, holat va izohlar (post ichida)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.core.audit import audit
from apps.core.notify import notify

from .models import ContentItem, ItemComment

DESIGN_STATUS = {"todo": "Bajarilishi kerak", "doing": "Jarayonda", "ready": "Tayyor — ko'rib chiqing", "revision": "Qayta ko'rib chiqing", "accepted": "Qabul qilindi"}
DESIGN_CLASS = {"todo": "warn", "doing": "blue", "ready": "ok", "revision": "bad", "accepted": "ok"}
OPEN = ("todo", "doing", "revision")


def name_of(u) -> str:
    return u.display() if u else "tizim"


def add_comment(item: ContentItem, user, text: str, kind: str = "comment") -> ItemComment | None:
    text = (text or "").strip()[:2000]
    if not text:
        return None
    return ItemComment.objects.create(item=item, user=user, kind=kind, text=text)


def _others(item: ContentItem, actor) -> list:
    users, seen = [], {getattr(actor, "pk", None)}
    for u in (item.assignee, item.created_by):
        if u and u.pk not in seen and u.is_active:
            users.append(u)
            seen.add(u.pk)
    return users


def mentioned(text: str, item: ContentItem, actor) -> list:
    """@username bilan tilga olinganlar (faqat shu biznesga kirishi borlar)."""
    import re
    from apps.accounts.models import User
    from apps.accounts.services import perms
    out = []
    for un in set(re.findall(r"@([\w.\-]{2,40})", text or "")):
        u = User.objects.filter(username=un, is_active=True).first()
        if u and u.pk != getattr(actor, "pk", None) and perms.has_business(u, item.business_id):
            out.append(u)
    return out


def comment(item: ContentItem, user, text: str) -> bool:
    c = add_comment(item, user, text)
    if not c:
        return False
    users = {u.pk: u for u in _others(item, user)}
    for u in mentioned(text, item, user):
        users[u.pk] = u
    if users:
        notify("design.status", f"Izoh: {item.title or 'post'}", f"{name_of(user)}: {c.text[:200]}", business_id=item.business_id,
               link=f"/kalendar/{item.pk}/#izohlar", users=list(users.values()))
    audit("content.comment", user=user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title})
    return True


def assign_task(item: ContentItem, user, *, assignee, due_at, brief: str) -> None:
    changed_assignee = (assignee.pk if assignee else None) != item.assignee_id
    item.assignee, item.due_at, item.brief = assignee, due_at, (brief or "").strip()
    item.design_status = "todo" if assignee else ""
    item.save(update_fields=["assignee", "due_at", "brief", "design_status", "updated_at"])
    bits = [f"mas'ul: {name_of(assignee)}" if assignee else "mas'ul olib tashlandi"]
    if due_at:
        from apps.core.utils import fmt_dt
        bits.append("muddat: " + fmt_dt(due_at))
    add_comment(item, user, "Vazifa berildi — " + ", ".join(bits), kind="status")
    audit("content.task", user=user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title, "name": name_of(assignee) if assignee else ""})
    if assignee and assignee.pk != getattr(user, "pk", None):
        from apps.core.utils import fmt_dt
        notify("task.assigned", f"Yangi vazifa: {item.title or 'post'}",
               (item.brief[:300] if item.brief else "Postga fayl tayyorlash kerak.") + (f"\nMuddat: {fmt_dt(due_at)}" if due_at else ""),
               business_id=item.business_id, link=f"/kalendar/{item.pk}/", users=[assignee], severity="warn" if due_at else "info")


def set_status(item: ContentItem, user, new: str, note: str = "") -> bool:
    if new not in DESIGN_STATUS or new == item.design_status:
        return False
    old = item.design_status
    item.design_status = new
    item.save(update_fields=["design_status", "updated_at"])
    add_comment(item, user, f"Holat: {DESIGN_STATUS.get(old, '—')} → {DESIGN_STATUS[new]}" + (f". {note.strip()}" if note.strip() else ""), kind="status")
    audit("content.design_status", user=user, business_id=item.business_id, target=f"item:{item.pk}", detail={"title": item.title, "status": new})
    titles = {"doing": "Dizayner boshladi", "ready": "Tayyor, ko'rib chiqing", "revision": "Qayta ko'rib chiqish so'raldi", "accepted": "Ish qabul qilindi", "todo": "Vazifa qayta ochildi"}
    notify("design.status", f"{titles[new]}: {item.title or 'post'}", f"{name_of(user)} · {DESIGN_STATUS[new]}" + (f"\n{note.strip()[:300]}" if note.strip() else ""),
           business_id=item.business_id, link=f"/kalendar/{item.pk}/", users=_others(item, user),
           severity="warn" if new == "revision" else "info")
    return True


def deadline_scan(now=None) -> int:
    """Muddati yaqin (3 soat) yoki o'tib ketgan ochiq vazifalar -> mas'ulga eslatma (kuniga 1-2 marta)."""
    now = now or timezone.now()
    n = 0
    qs = ContentItem.objects.filter(design_status__in=OPEN, due_at__isnull=False, due_at__lte=now + timedelta(hours=3), assignee__isnull=False).select_related("assignee", "business")
    for it in qs:
        late = it.due_at < now
        from apps.core.utils import fmt_dt
        n += notify("design.status", ("⏰ Muddat o'tdi: " if late else "⏳ Muddat yaqin: ") + (it.title or "post"),
                    f"Muddat: {fmt_dt(it.due_at)}. Tayyor bo'lsa «Tayyor» tugmasini bosing.", business_id=it.business_id, link=f"/kalendar/{it.pk}/",
                    severity="critical" if late else "warn", users=[it.assignee], dedupe_key=f"dl:{it.pk}:{'late' if late else 'soon'}:{timezone.localdate()}",
                    dedupe_minutes=60 * 12)
    return n
