from __future__ import annotations

from django.http import Http404

from apps.accounts.services import perms


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
