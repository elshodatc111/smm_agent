from __future__ import annotations

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect

from apps.accounts.services import perms


def need_business(request, code: str | None = None):
    """Tanlangan biznesni qaytaradi; tanlanmagan bo'lsa None (view o'zi ro'yxat/yo'naltirishni hal qiladi)."""
    return getattr(request, "business", None)


def ask_pick_business(request, what: str = "Bu sahifa"):
    messages.info(request, f"{what} uchun yuqoridan bitta biznesni tanlang.")
    return redirect("dashboard")


def get_obj(request, model, pk, code: str, *, business_field: str = "business"):
    """Obyektni oladi va (server tomonda) biznes kirishi + ruxsatni tekshiradi; aks holda 404/403."""
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise Http404
    biz = getattr(obj, business_field, None)
    biz_id = getattr(obj, f"{business_field}_id", None)
    if biz_id is not None and not perms.has_business(request.user, biz_id):
        raise Http404
    if not perms.can(request.user, code, biz or biz_id):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    return obj


STATUS_CLASS = {"active": "ok", "published": "ok", "done": "ok", "ready": "ok", "sent": "ok", "good": "ok", "approved": "blue",
                "scheduled": "blue", "pending_approval": "warn", "token_expiring": "warn", "paused": "warn", "cooldown": "warn",
                "awaiting_approval": "warn", "running": "blue", "pending": "", "draft": "", "error": "bad", "failed": "bad", "blocked": "bad"}
