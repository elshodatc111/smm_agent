

from apps.connections.models import Competitor, SocialAccount
from apps.connections.registry import get_connector
from apps.jobs.queue import JobContext, register_handler

from . import collector
from .models import Post, PostMetricsHistory


@register_handler("collect_account", "collect")
def collect_account(ctx: JobContext):
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    if not acc.is_collectable:
        return {"skipped": True}
    return collector.collect_account(acc, mode=ctx.payload.get("mode", "regular"), days=ctx.payload.get("days"),
                                     progress=ctx.report_progress)


@register_handler("historical_import", "collect")
def historical_import(ctx: JobContext):
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    return collector.collect_account(acc, mode="history", days=ctx.payload.get("days", 90), progress=ctx.report_progress)


@register_handler("story_snapshot", "collect")
def story_snapshot(ctx: JobContext):
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    return {"stories": collector.snapshot_stories(acc)} if acc.is_collectable else {"skipped": True}


@register_handler("story_deep", "collect")
def story_deep(ctx: JobContext):
    """Story 20 soatdan oshgach to'liq yig'ish (reach, javoblar, follows, navigatsiya...)."""
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    return {"stories": collector.snapshot_stories(acc, deep=True)} if acc.is_collectable else {"skipped": True}


@register_handler("collect_post_metrics", "collect")
def collect_post_metrics(ctx: JobContext):
    from .collector import compute_er
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    posts = Post.objects.filter(account=acc, external_id__in=ctx.payload.get("post_ids", []))
    conn = get_connector(acc)
    by = {p.external_id: p for p in posts}
    n = 0
    for m in conn.fetch_post_metrics(list(by)):
        p = by[m.external_id]
        er, basis = compute_er(m, None)
        PostMetricsHistory.objects.create(post=p, business_id=acc.business_id, taken_at=m.taken_at, views=m.views, likes=m.likes,
                                          comments=m.comments, shares=m.shares, saves=m.saves, reach=m.reach, reactions=m.reactions,
                                          watch_time_sec=m.watch_time_sec, avg_view_duration_sec=m.avg_view_duration_sec,
                                          er=er, er_basis=basis, age_hours=(m.taken_at - p.published_at).total_seconds() / 3600)
        n += 1
    return {"snapshots": n}


@register_handler("collect_competitor", "collect")
def collect_competitor(ctx: JobContext):
    comp = Competitor.objects.get(pk=ctx.payload["competitor_id"])
    return collector.collect_competitor(comp, ctx.payload.get("depth", "light"))


@register_handler("token_refresh", "system")
def token_refresh(ctx: JobContext):
    acc = SocialAccount.objects.get(pk=ctx.payload["connection_id"])
    conn = get_connector(acc)
    cred = conn.refresh_credentials()
    if cred is None:
        return {"refreshed": False}
    data = {**acc.credentials(), **cred.data}
    acc.set_credentials(data)
    acc.token_expires_at = cred.expires_at
    if acc.status == "token_expiring":
        acc.status = "active"
    acc.save(update_fields=["credentials_enc", "token_expires_at", "status"])
    return {"refreshed": True, "expires_at": cred.expires_at.isoformat() if cred.expires_at else None}


@register_handler("daily_rollup", "system")
def daily_rollup(ctx: JobContext):
    from . import daily
    p = ctx.payload or {}
    return {"rows": daily.rollup_all(backfill_days=int(p.get("backfill_days", 0)))}


@register_handler("daily_rollup_day", "system")
def daily_rollup_day(ctx: JobContext):
    from datetime import date
    from . import daily
    return {"rows": daily.rollup_all(day=date.fromisoformat(ctx.payload["day"]))}
