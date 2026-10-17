from django import template

register = template.Library()
_B = {"new": "", "phone": "blue", "interested": "violet", "waiting": "warn", "sold": "ok", "lost": "bad", "pending": "warn", "approved": "ok",
      "rejected": "bad", "active": "ok", "expired": "", "cancelled": "bad", "draft": "warn", "paused": ""}


@register.filter
def money(v):
    try:
        return f"{int(v):,}".replace(",", " ")
    except (TypeError, ValueError):
        return v


@register.filter
def bcls(status):
    return _B.get(status, "")
