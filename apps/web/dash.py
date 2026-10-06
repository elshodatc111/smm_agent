"""Boshqaruv paneli ma'lumotlari: har bir ulanish (akkaunt) bo'yicha alohida ko'rsatkichlar."""
from __future__ import annotations

from django.utils import timezone

from apps.content.models import ContentTarget
from apps.core.utils import fmt_dt
from apps.metrics import analytics as an
from apps.metrics.models import Post


def _num(v):
    return None if v is None else round(v, 4) if isinstance(v, float) else v


def scheduled_count(account) -> int:
    """Akkauntga rejalashtirilgan (hali chiqmagan) postlar soni."""
    return ContentTarget.objects.filter(account=account, status="pending", item__status__in=["scheduled", "approved"],
                                        item__deleted_at__isnull=True, item__scheduled_at__gte=timezone.now()).count()


def account_row(business, account, days: int = 30) -> dict:
    c = an.compare_periods(business, days, [account.pk])
    k, d = c["current"], c["delta_pct"]
    return {"id": account.pk, "name": account.name, "handle": account.handle, "platform": account.platform,
            "platform_label": account.get_platform_display(), "status": account.status, "status_label": account.get_status_display(),
            "error": account.last_error, "last_collect": fmt_dt(account.last_collect_at) if account.last_collect_at else "",
            "token_until": account.token_expires_at.strftime("%d.%m.%Y") if account.token_expires_at else "",
            "followers": k["followers"], "followers_delta": k["followers_delta"], "views": k["views"], "views_delta": _num(d.get("views")),
            "er": _num(k["er"]), "posts": k["posts"], "posts_total": Post.objects.filter(account=account).count(),
            "scheduled": scheduled_count(account), "likes": k["likes"], "comments": k["comments"]}


def kpi_json(k: dict, delta: dict) -> dict:
    return {"followers": k["followers"], "followers_delta": k["followers_delta"], "views": k["views"], "views_delta": _num(delta.get("views")),
            "er": _num(k["er"]), "posts": k["posts"], "reach": k["reach"], "likes": k["likes"], "comments": k["comments"]}


def post_json(r) -> dict:
    p = r.post
    return {"id": p.pk, "text": (p.text or "")[:90], "er": _num(r.er), "views": r.views, "likes": r.likes, "platform": p.platform,
            "media_type": p.media_type, "date": fmt_dt(p.published_at)}
