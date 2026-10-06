"""Kunlik statistika: har kuni (va kechasi yakuniy) biznes/akkaunt bo'yicha qator saqlanadi — obunachi, lid, ko'rish va h.k. tarixi."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from apps.core.utils import tz

from .models import AccountMetrics, DailyStat, Post, Story


def _bounds(day: date):
    z = tz()
    a = datetime.combine(day, time(0, 0), tzinfo=z)
    return a, a + timedelta(days=1)


def _followers_at(account, end):
    m = AccountMetrics.objects.filter(account=account, taken_at__lt=end, followers__isnull=False).order_by("-taken_at").first()
    return m.followers if m else None


def _post_sums(posts_qs):
    from .analytics import latest_metrics_qs
    ids = list(posts_qs.values_list("pk", flat=True))
    if not ids:
        return dict(views=0, reach=0, likes=0, comments=0, shares=0, saves=0)
    rows = latest_metrics_qs().filter(post_id__in=ids)
    agg = rows.aggregate(v=Sum("views"), r=Sum("reach"), l=Sum("likes"), c=Sum("comments"), s=Sum("shares"), sv=Sum("saves"))
    return dict(views=agg["v"] or 0, reach=agg["r"] or 0, likes=agg["l"] or 0, comments=agg["c"] or 0, shares=agg["s"] or 0, saves=agg["sv"] or 0)


def _story_views(stories_qs):
    total = 0
    for st in stories_qs:
        h = st.history.order_by("-is_final", "-taken_at").first()
        total += (h.views or 0) if h else 0
    return total


def _clicks(business_id, a, b):
    try:
        from apps.links.models import LinkClick
        return LinkClick.objects.filter(link__business_id=business_id, clicked_at__gte=a, clicked_at__lt=b).count()
    except Exception:  # noqa: BLE001
        return 0


def rollup_business(business, day: date) -> int:
    a, b = _bounds(day)
    n = 0
    tot = dict(followers=0, followers_delta=0, posts=0, stories=0, views=0, reach=0, likes=0, comments=0, shares=0, saves=0, story_views=0)
    have_f = False
    for acc in business.accounts.filter(archived_at__isnull=True):
        f = _followers_at(acc, b)
        prev_f = _followers_at(acc, a)
        posts = Post.objects.filter(account=acc, published_at__gte=a, published_at__lt=b)
        stories = Story.objects.filter(account=acc, published_at__gte=a, published_at__lt=b)
        vals = dict(platform=acc.platform, followers=f, followers_delta=(f - prev_f) if f is not None and prev_f is not None else 0,
                    posts=posts.count(), stories=stories.count(), story_views=_story_views(stories), **_post_sums(posts))
        DailyStat.objects.update_or_create(business=business, account=acc, day=day, defaults=vals)
        n += 1
        if f is not None:
            have_f = True
            tot["followers"] += f
        for k in ("followers_delta", "posts", "stories", "views", "reach", "likes", "comments", "shares", "saves", "story_views"):
            tot[k] += vals[k]
    DailyStat.objects.update_or_create(business=business, account=None, day=day, defaults=dict(
        platform="", followers=tot["followers"] if have_f else None, followers_delta=tot["followers_delta"], posts=tot["posts"], stories=tot["stories"],
        views=tot["views"], reach=tot["reach"], likes=tot["likes"], comments=tot["comments"], shares=tot["shares"], saves=tot["saves"],
        story_views=tot["story_views"], link_clicks=_clicks(business.pk, a, b)))
    return n + 1


def rollup_all(day: date | None = None, backfill_days: int = 0) -> int:
    from apps.businesses.models import Business
    today = timezone.localtime(timezone.now(), tz()).date()
    days = [today - timedelta(days=i) for i in range(backfill_days, -1, -1)] if backfill_days else [day or today]
    n = 0
    for b in Business.objects.all():
        for d in days:
            n += rollup_business(b, d)
    return n


def series(business, days: int = 30, account=None) -> list[DailyStat]:
    since = timezone.localtime(timezone.now(), tz()).date() - timedelta(days=days - 1)
    return list(DailyStat.objects.filter(business=business, account=account, day__gte=since).order_by("day"))
