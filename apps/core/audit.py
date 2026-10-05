from .logging_utils import scrub


def audit(action: str, *, user=None, business_id=None, target: str = "", detail: dict | None = None) -> None:
    from .models import AuditLog
    d = {k: (scrub(v) if isinstance(v, str) else v) for k, v in (detail or {}).items()}
    AuditLog.objects.create(user=user if getattr(user, "pk", None) else None, business_id=business_id,
                            action=action, target=target[:200], detail=d)
