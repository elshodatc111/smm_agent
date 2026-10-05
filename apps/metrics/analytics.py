"""Tahlil: KPI, dinamika, eng yaxshi kontent, vaqt, anomaliya. Formulalar CONTRACTS §11.1."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.core.utils import local

from .models import AccountMetrics, Post, PostMetricsHistory


def latest_metrics_qs(business_id=None, account_id=None, since=None, until=None, platform=None):
    """Har post uchun eng so'nggi snapshot (PostMetricsHistory)."""
    latest = PostMetricsHistory.objects.filter(post=OuterRef("post")).order_by("-taken_at").values("pk")[:1]
    qs = PostMetricsHistory.objects.filter(pk=Subquery(latest))
    if business_id:
        qs = qs.filter(business_id=business_id)
    if account_id:
        qs = qs.filter(post__account_id=account_id)
    if platform:
        qs = qs.filter(post__platform=platform)
    if since:
        qs = qs.filter(post__published_at__gte=since)
    if until:
        qs = qs.filter(post__published_at__lt=until)
    return qs.select_related("post")


def _sum(rows, f):
    return sum(getattr(r, f) or 0 for r in rows)


def period_kpis(business, since: datetime, until: datetime, account_ids=None) -> dict:
    accounts = business.accounts.filter(archived_at__isnull=True)
    if account_ids:
        accounts = accounts.filter(pk__in=account_ids)
    followers_now = followers_start = 0
    for a in accounts:
        last = AccountMetrics.objects.filter(account=a, taken_at__lt=until).order_by("-taken_at").first()
        first = AccountMetrics.objects.filter(account=a, taken_at__gte=since).order_by("taken_at").first() or last
        followers_now += (last.followers or 0) if last else 0
        followers_start += (first.followers or 0) if first else 0
    rows = list(latest_metrics_qs(business.pk, since=since, until=until).filter(post__account__in=accounts))
    ers = [r.er for r in rows if r.er is not None]
    return {"followers": followers_now, "followers_delta": followers_now - followers_start,
            "followers_growth_pct": (100 * (followers_now - followers_start) / followers_start) if followers_start else None,
            "posts": len(rows), "views": _sum(rows, "views"), "reach": _sum(rows, "reach"),
            "likes": _sum(rows, "likes"), "comments": _sum(rows, "comments"), "shares": _sum(rows, "shares"),
            "saves": _sum(rows, "saves"), "er": (sum(ers) / len(ers)) if ers else None}


def compare_periods(business, days: int = 30, account_ids=None) -> dict:
    now = timezone.now()
    cur = period_kpis(business, now - timedelta(days=days), now, account_ids)
    prev = period_kpis(business, now - timedelta(days=2 * days), now - timedelta(days=days), account_ids)
    delta = {}
    for k, v in cur.items():
        pv = prev.get(k)
        delta[k] = ((v - pv) / pv * 100) if isinstance(v, (int, float)) and isinstance(pv, (int, float)) and pv else None
    return {"current": cur, "previous": prev, "delta_pct": delta}


def follower_series(account, days: int = 30) -> list[dict]:
    since = timezone.now() - timedelta(days=days)
    by_day = {}
    for m in AccountMetrics.objects.filter(account=account, taken_at__gte=since).order_by("taken_at"):
        by_day[local(m.taken_at).date()] = m.followers
    return [{"date": d.isoformat(), "followers": v} for d, v in sorted(by_day.items())]


def business_follower_series(business, days: int = 30) -> list[dict]:
    totals = defaultdict(int)
    for a in business.accounts.filter(archived_at__isnull=True):
        for p in follower_series(a, days):
            totals[p["date"]] += p["followers"] or 0
    return [{"date": d, "followers": v} for d, v in sorted(totals.items())]


def top_posts(business, n: int = 5, worst: bool = False, days: int = 30, account_id=None, platform=None, media_type=None):
    rows = list(latest_metrics_qs(business.pk, account_id=account_id, since=timezone.now() - timedelta(days=days), platform=platform).exclude(er=None))
    if media_type:
        rows = [r for r in rows if r.post.media_type == media_type]
    rows.sort(key=lambda r: r.er, reverse=not worst)
    return rows[:n]


def by_type(business, days: int = 60, platform=None):
    groups = defaultdict(list)
    for r in latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=days), platform=platform):
        groups[r.post.media_type].append(r)
    out = []
    for t, rows in groups.items():
        ers = [r.er for r in rows if r.er is not None]
        out.append({"type": t, "count": len(rows), "avg_views": _sum(rows, "views") / len(rows),
                    "avg_er": sum(ers) / len(ers) if ers else None})
    return sorted(out, key=lambda x: -(x["avg_er"] or 0))


def best_times(business, days: int = 90, platform=None, media_type=None):
    """Hafta kuni va soat bo'yicha o'rtacha ER."""
    wd, hr = defaultdict(list), defaultdict(list)
    for r in latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=days), platform=platform).exclude(er=None):
        if media_type and r.post.media_type != media_type:
            continue
        t = local(r.post.published_at)
        wd[t.weekday()].append(r.er)
        hr[t.hour].append(r.er)
    avg = lambda d: sorted(((k, sum(v) / len(v), len(v)) for k, v in d.items()), key=lambda x: -x[1])
    return {"weekday": avg(wd), "hour": avg(hr)}


def hashtag_stats(business, days: int = 90, top: int = 10, platform=None):
    tags = defaultdict(list)
    for r in latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=days), platform=platform).exclude(er=None):
        for h in r.post.hashtags or []:
            tags[h.lower()].append(r.er)
    return sorted(({"tag": t, "count": len(v), "avg_er": sum(v) / len(v)} for t, v in tags.items() if len(v) >= 2),
                  key=lambda x: -x["avg_er"])[:top]


def post_frequency(business, days: int = 30):
    n = Post.objects.filter(business=business, published_at__gte=timezone.now() - timedelta(days=days)).count()
    return {"posts": n, "per_week": n / (days / 7)}


def median_baseline(business, days: int = 30):
    rows = list(latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=days)))
    ers = [r.er for r in rows if r.er is not None]
    views = [r.views for r in rows if r.views is not None]
    return {"er": statistics.median(ers) if ers else None, "views": statistics.median(views) if views else None, "n": len(rows)}


def is_winner(row: PostMetricsHistory, baseline: dict) -> bool:
    mult = float(get_setting("analytics.winner_multiplier", 1.5))
    return bool(row.er is not None and baseline["er"] and row.er > mult * baseline["er"]
                and row.views is not None and baseline["views"] and row.views > mult * baseline["views"])


def detect_anomalies(account, window: int = 28):
    """Obunachi kunlik o'zgarishi z-score. |z| >= analytics.anomaly_z bo'lsa xabar beriladi."""
    series = follower_series(account, window + 2)
    if len(series) < 7:
        return None
    diffs = [b["followers"] - a["followers"] for a, b in zip(series, series[1:]) if a["followers"] is not None and b["followers"] is not None]
    if len(diffs) < 6:
        return None
    hist, last = diffs[:-1], diffs[-1]
    sd = statistics.pstdev(hist) or 1.0
    z = (last - statistics.mean(hist)) / sd
    thr = float(get_setting("analytics.anomaly_z", 2.5))
    return {"z": z, "delta": last, "direction": "o'sish" if z > 0 else "pasayish"} if abs(z) >= thr else None


def numeric_basis(post: Post) -> dict:
    """«Nega ishladi» uchun AI'ga beriladigan RAQAMLI asos (AI taxmin qilmasin)."""
    last = post.history.order_by("-taken_at").first()
    if not last:
        return {}
    base = median_baseline(post.business)
    t = local(post.published_at)
    return {"vaqt": f"{t:%A %H:%M}", "format": post.media_type, "davomiylik_sek": post.duration_sec,
            "matn_uzunligi": len(post.text or ""), "hashtaglar": len(post.hashtags or []),
            "views": last.views, "reach": last.reach, "likes": last.likes, "comments": last.comments,
            "shares": last.shares, "saves": last.saves, "er": last.er, "er_asosi": last.er_basis,
            "biznes_median_er": base["er"], "biznes_median_views": base["views"],
            "er_nisbati": (last.er / base["er"]) if last.er and base["er"] else None,
            "views_nisbati": (last.views / base["views"]) if last.views and base["views"] else None}
