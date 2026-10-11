from django import template

register = template.Library()


@register.filter
def dictkey(d, k):
    try:
        return d.get(k)
    except AttributeError:
        return None


@register.filter
def attr(o, name):
    return getattr(o, name, None) if o is not None else None


@register.filter
def pct(v, digits=1):
    try:
        return f"{float(v) * 100:.{int(digits)}f}%"
    except (TypeError, ValueError):
        return "—"


@register.filter
def num(v):
    try:
        return f"{int(v):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


@register.filter
def split(v, sep=","):
    return str(v).split(sep)


@register.filter
def get_item(d, key):
    try:
        return d.get(key, "#64748b")
    except AttributeError:
        return "#64748b"


@register.filter
def gfmt(v, metric):
    from apps.goals.services import fmt
    return fmt(v, metric)


@register.filter
def platdot(platform):
    return {"telegram": "tg", "instagram": "ig", "youtube": "yt"}.get(platform, "")


@register.filter
def clamp100(v):
    try:
        return max(0, min(100, float(v)))
    except (TypeError, ValueError):
        return 0
