"""Ma'lumot yig'ish (collector). O'z hisoblar: rasmiy API; raqobatchilar: ProviderRouter."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from apps.connections.base import (AuthError, Capability, PlatformError, Platform, RateLimitError,
                                   TokenExpiredError)
from apps.connections.models import Competitor, SocialAccount
from apps.connections.registry import get_connector
from apps.core.notify import notify
from apps.core.settings_store import get_setting

from .models import (AccountMetrics, CollectionRun, Comment, CompetitorMetrics, CompetitorPost,
                     CompetitorPostMetric, Post, PostMetricsHistory, Story, StoryMetricsHistory)

log = logging.getLogger(__name__)


def compute_er(m, followers: int | None) -> tuple[float | None, str]:
    """ER_post = (like+comment+share+save) / maxraj. Maxraj: reach > views > followers.
    Himoya: o'zaro ta'sirlar maxrajdan oshib ketsa (ma'lumot nomuvofiq: masalan reach yo'q, views=1) shu maxraj
    ishonchsiz hisoblanib keyingisiga o'tiladi; natija hech qachon 100% dan oshmaydi."""
    inter = sum(x or 0 for x in (m.likes, m.comments, m.shares, m.saves))
    for basis, den in (("reach", m.reach), ("views", m.views), ("followers", followers)):
        if den and den > 0 and inter <= den:
            return inter / den, basis
    return None, ""


def _mark_error(acc: SocialAccount, err: Exception) -> None:
    acc.last_error = (getattr(err, "user_message_uz", None) or str(err))[:400]
    if isinstance(err, (AuthError, TokenExpiredError)):
        acc.status = "error"
        notify("token.expiring", f"Ulanish uzildi: {acc.name}", acc.last_error, business_id=acc.business_id,
               severity="critical", dedupe_key=f"autherr:{acc.pk}", link=f"/ulanishlar/{acc.pk}/")
    acc.save(update_fields=["last_error", "status"])


def _post_age_rule(age_h: float, hour_slot: bool, daily_slot: bool, weekly: bool) -> bool:
    """Qaysi postlar uchun metrika snapshot'i olinadi (API tejash)."""
    if age_h <= 48:
        return True
    if age_h <= 24 * 7:
        return daily_slot
    if age_h <= 24 * 30:
        return weekly
    return False


def collect_account(acc: SocialAccount, *, mode: str = "regular", days: int | None = None, progress=None) -> dict:
    """Bitta hisob uchun to'liq yig'ish. Qaytaradi: statistik natija."""
    t0 = timezone.now()
    conn = get_connector(acc)
    run = CollectionRun(business_id=acc.business_id, account=acc, kind=f"account:{mode}")
    items = 0
    try:
        stats = conn.fetch_account_stats()
        AccountMetrics.objects.create(business=acc.business, account=acc, taken_at=stats.taken_at, followers=stats.followers,
                                      following=stats.following, posts_count=stats.posts_count, reach=stats.reach,
                                      impressions=stats.impressions, views=stats.views, profile_visits=stats.profile_visits,
                                      extra=stats.extra)
        items += 1
        if progress:
            progress(10)
        since_days = (days or int(get_setting("collect.history_days", 365))) if mode == "history" else 14
        since = timezone.now() - timedelta(days=since_days)
        new_posts, cursor, pages = [], None, 0
        while Capability.POSTS in conn.capabilities:
            page = conn.fetch_posts(since, cursor)
            for pd in page.items:
                post, created = Post.objects.get_or_create(
                    platform=acc.platform, external_id=pd.external_id,
                    defaults=dict(business=acc.business, account=acc, media_type=str(pd.media_type), text=pd.text or "",
                                  url=pd.url or "", published_at=pd.published_at, duration_sec=pd.duration_sec,
                                  hashtags=pd.hashtags, media_urls=pd.media_urls[:3]))
                new_posts.append(post)
                items += created
            pages += 1
            if progress:
                progress(10 + min(40, pages * 8))
            if not page.next_cursor or pages >= 20:
                break
            cursor = page.next_cursor
        # Hisobda hali birorta post yo'q bo'lsa (masalan, videolar eski) — davrdan qat'i nazar oxirgi postlarni olamiz
        if Capability.POSTS in conn.capabilities and not Post.objects.filter(account=acc).exists():
            cursor, pages = None, 0
            while pages < 2:
                page = conn.fetch_posts(timezone.now() - timedelta(days=3650), cursor)
                for pd in page.items:
                    post, created = Post.objects.get_or_create(
                        platform=acc.platform, external_id=pd.external_id,
                        defaults=dict(business=acc.business, account=acc, media_type=str(pd.media_type), text=pd.text or "",
                                      url=pd.url or "", published_at=pd.published_at, duration_sec=pd.duration_sec,
                                      hashtags=pd.hashtags, media_urls=pd.media_urls[:3]))
                    items += created
                pages += 1
                if not page.next_cursor:
                    break
                cursor = page.next_cursor
            since = timezone.now() - timedelta(days=3650)
        # metrika snapshot'lari
        now = timezone.now()
        daily_slot = now.hour < 12
        weekly = now.weekday() == 0 and daily_slot
        qs = Post.objects.filter(account=acc, published_at__gte=since)
        todo = [p for p in qs if mode == "history" or _post_age_rule((now - p.published_at).total_seconds() / 3600, True, daily_slot, weekly)]
        if mode == "history":
            todo = todo[:200]
        followers = stats.followers
        if todo and Capability.STATS in conn.capabilities:
            by_id = {p.external_id: p for p in todo}
            ids = list(by_id)
            for i in range(0, len(ids), 20):
                for m in conn.fetch_post_metrics(ids[i:i + 20]):
                    p = by_id.get(m.external_id)
                    if not p:
                        continue
                    er, basis = compute_er(m, followers)
                    PostMetricsHistory.objects.create(
                        post=p, business_id=acc.business_id, taken_at=m.taken_at, views=m.views, likes=m.likes,
                        comments=m.comments, shares=m.shares, saves=m.saves, reach=m.reach, reactions=m.reactions,
                        watch_time_sec=m.watch_time_sec, avg_view_duration_sec=m.avg_view_duration_sec, ctr=m.ctr,
                        er=er, er_basis=basis, age_hours=(m.taken_at - p.published_at).total_seconds() / 3600, extra=m.extra)
                    items += 1
                if progress:
                    progress(50 + int(45 * min(i + 20, len(ids)) / max(1, len(ids))))
        # izohlar (yangi postlar uchun)
        if Capability.COMMENTS in conn.capabilities and mode == "regular":
            for p in [p for p in qs if (now - p.published_at) <= timedelta(days=7)][:15]:
                try:
                    for c in conn.fetch_comments(p.external_id, now - timedelta(days=8)).items:
                        _, created = Comment.objects.get_or_create(
                            post=p, external_id=c.external_id,
                            defaults=dict(business=acc.business, account=acc, author=c.author_name or "", text=c.text,
                                          created_at=c.created_at, like_count=c.like_count))
                        items += created
                except PlatformError as e:
                    log.info("izoh yig'ib bo'lmadi %s: %s", p.external_id, e)
        acc.last_collect_at, acc.last_error = timezone.now(), ""
        if acc.status == "error":
            acc.status = "active"
        acc.save(update_fields=["last_collect_at", "last_error", "status"])
        if mode == "history":
            acc.history_imported = True
            acc.save(update_fields=["history_imported"])
        run.ok, run.items = True, items
        return {"items": items, "followers": followers}
    except RateLimitError:
        run.ok, run.error = False, "rate_limit"
        raise
    except PlatformError as e:
        run.ok, run.error = False, str(e)[:400]
        _mark_error(acc, e)
        raise
    finally:
        run.duration_ms = (timezone.now() - t0).total_seconds() * 1000
        run.items = items
        run.save()


def snapshot_stories(acc: SocialAccount, deep: bool = False) -> int:
    """Story statistikasi: odatda har soat; 20 soatdan keyin (deep) — to'liq yig'ish (har ~20 daqiqada, navigatsiya bilan).
    Muddati tugagach yakuniy qator saqlanadi."""
    conn = get_connector(acc)
    if Capability.STORIES not in conn.capabilities:
        return 0
    now = timezone.now()
    n = 0
    live = conn.fetch_stories()
    if deep:
        after = timedelta(hours=float(get_setting("collect.story_deep_after_hours", 20)))
        live = [sd for sd in live if now - sd.published_at >= after]
    for sd in live:
        st, _ = Story.objects.get_or_create(account=acc, external_id=sd.external_id, defaults=dict(
            business=acc.business, published_at=sd.published_at, expires_at=sd.published_at + timedelta(hours=24), url=sd.url or ""))
    ids = [s.external_id for s in live]
    if not ids:
        got = []
    elif deep:
        try:
            got = conn.fetch_story_metrics(ids, deep=True)
        except TypeError:
            got = conn.fetch_story_metrics(ids)
    else:
        got = conn.fetch_story_metrics(ids)
    for m in got:
        st = Story.objects.get(account=acc, external_id=m.external_id)
        StoryMetricsHistory.objects.create(story=st, taken_at=m.taken_at, views=m.views, reach=m.reach, replies=m.comments,
                                           shares=m.shares, extra=m.extra)
        n += 1
    # tugagan storilar: yakuniy ko'rsatkich
    for st in Story.objects.filter(account=acc, finalized=False, expires_at__lte=now):
        last = st.history.order_by("-taken_at").first()
        if last:
            StoryMetricsHistory.objects.create(story=st, taken_at=now, views=last.views, reach=last.reach, replies=last.replies,
                                               shares=last.shares, extra=last.extra, is_final=True)
        st.finalized = True
        st.save(update_fields=["finalized"])
    return n


def _extract_posts(platform: str, data) -> list[dict]:
    """Provayder javobini umumiy ko'rinishga keltiradi (ScrapeCreators/Data API/t.me)."""
    if isinstance(data, dict):
        for k in ("videos", "posts", "items", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    out = []
    if not isinstance(data, list):
        return out
    for i, d in enumerate(data):
        if not isinstance(d, dict):
            continue
        pid = str(d.get("id") or d.get("videoId") or d.get("shortcode") or d.get("code") or i)
        pub = d.get("published_at") or d.get("publishedTimeText") or d.get("taken_at") or d.get("date")
        try:
            when = datetime.fromisoformat(str(pub).replace("Z", "+00:00")) if pub and "T" in str(pub) else None
        except ValueError:
            when = None
        out.append({"id": pid, "text": d.get("text") or d.get("title") or d.get("caption") or "",
                    "views": _i(d.get("views") or d.get("viewCountInt") or d.get("video_view_count") or d.get("play_count")),
                    "likes": _i(d.get("likes") or d.get("like_count") or d.get("likeCountInt")),
                    "comments": _i(d.get("comments") or d.get("comment_count") or d.get("commentCountInt")),
                    "published_at": when, "type": d.get("type") or d.get("media_type") or ""})
    return out


def _i(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _followers_from(data) -> int | None:
    if isinstance(data, dict):
        for k in ("followers", "subscriberCount", "subscriber_count", "follower_count", "edge_followed_by"):
            v = data.get(k)
            if isinstance(v, dict):
                v = v.get("count")
            if v is not None:
                return _i(v)
    return None


def collect_competitor(comp: Competitor, depth: str = "light") -> dict:
    """Raqobatchi: light = profil, full = profil + postlar. Hammasi ProviderRouter orqali (kvota/kredit himoyasi)."""
    from apps.providers.base import DataKind, DataRequest, NoProviderAvailable
    from apps.providers.router import ProviderRouter
    router = ProviderRouter()
    plat = Platform(comp.platform)
    t0 = timezone.now()
    cost, unit, prov, items = 0.0, "", "", 0
    run = CollectionRun(business_id=comp.business_id, competitor=comp, kind=f"competitor:{depth}")
    try:
        r = router.fetch(DataRequest(plat, DataKind.PROFILE, comp.handle))
        prov, cost, unit = r.provider, cost + r.cost.amount, r.cost.unit
        views = r.data.get("views") if isinstance(r.data, dict) else None
        CompetitorMetrics.objects.create(competitor=comp, business_id=comp.business_id, taken_at=timezone.now(),
                                         followers=_followers_from(r.data), posts_count=_i(r.data.get("posts_count")) if isinstance(r.data, dict) else None,
                                         views=_i(views), provider=r.provider)
        items += 1
        comp.last_light_at = timezone.now()
        if depth == "full":
            kind = DataKind.VIDEO_LIST if plat == Platform.YOUTUBE else DataKind.POSTS
            pr = router.fetch(DataRequest(plat, kind, comp.handle, limit=20))
            cost += pr.cost.amount
            for d in _extract_posts(comp.platform, pr.data):
                cp, _ = CompetitorPost.objects.update_or_create(
                    competitor=comp, external_id=d["id"],
                    defaults=dict(business_id=comp.business_id, text=d["text"][:4000], published_at=d["published_at"], media_type=str(d["type"])[:12],
                                  views=d["views"], likes=d["likes"], comments=d["comments"]))
                CompetitorPostMetric.objects.create(post=cp, taken_at=timezone.now(), views=d["views"], likes=d["likes"], comments=d["comments"])
                items += 1
            comp.last_full_at = timezone.now()
            try:
                check_competitor_hits(comp)
            except Exception:  # noqa: BLE001 — ogohlantirish xatosi yig'ishni to'xtatmasin
                pass
        comp.save(update_fields=["last_light_at", "last_full_at"])
        run.provider, run.cost, run.cost_unit = prov, cost, unit
        return {"items": items, "cost": cost}
    except NoProviderAvailable:
        run.ok, run.error = False, "provayder yo'q"
        raise
    except PlatformError as e:
        run.ok, run.error = False, str(e)[:400]
        raise
    finally:
        run.items = items
        run.duration_ms = (timezone.now() - t0).total_seconds() * 1000
        run.save()


def _perf(p) -> float:
    """Post «kuchi»: ko'rishlar bo'lsa shu, bo'lmasa layk + 3*izoh."""
    if p.views:
        return float(p.views)
    return float((p.likes or 0) + 3 * (p.comments or 0))


def check_competitor_hits(comp: Competitor) -> int:
    """Raqobatchining yangi posti o'zining odatiy natijasidan ancha yaxshi chiqsa — ogohlantiradi (har post uchun bir marta)."""
    from datetime import timedelta
    from statistics import median
    from apps.core.notify import notify
    from apps.core.settings_store import get_setting
    posts = list(CompetitorPost.objects.filter(competitor=comp).order_by("-published_at")[:30])
    if len(posts) < 5:
        return 0
    mult = float(get_setting("competitor.hit_multiplier", 2.0))
    now = timezone.now()
    n = 0
    for p in posts:
        if p.alerted:
            continue
        others = [_perf(x) for x in posts if x.pk != p.pk and _perf(x) > 0]
        base = median(others) if len(others) >= 4 else 0
        perf = _perf(p)
        fresh = p.published_at and p.published_at >= now - timedelta(days=7)
        hit = base > 0 and perf >= base * mult and perf >= (300 if p.views else 30)
        if hit and fresh:
            txt = " ".join((p.text or "").split())[:140] or "(matnsiz)"
            metric = f"{int(p.views):,} ko'rish".replace(",", " ") if p.views else f"{p.likes or 0} layk, {p.comments or 0} izoh"
            notify("competitor.hit", f"Raqobatchi posti yaxshi chiqdi: {comp.name or comp.handle}",
                   f"{metric} — odatdagidan {perf / base:.1f} baravar ko'p. Tur: {p.media_type or '—'}.\n«{txt}»\nUning g'oyasini o'zingizcha, o'z uslubingizda ishlatib ko'ring.",
                   business_id=comp.business_id, severity="info", link="/raqobatchilar/", dedupe_key=f"comp-hit:{p.pk}")
            n += 1
        if hit or not fresh:
            p.alerted = True      # eski postlar uchun ogohlantirish yuborilmaydi (birinchi yig'ishda spam bo'lmasin)
            p.save(update_fields=["alerted"])
    return n
