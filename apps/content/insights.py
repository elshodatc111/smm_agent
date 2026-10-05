"""Nashr vaqti tavsiyasi va AI uchun tahlil konteksti (faqat o'z ma'lumotlari, AIsiz)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.utils import local, tz

WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]
UZ_MON = ["", "yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"]

# Ma'lumot yetarli bo'lmaganda umumiy tavsiya: soat -> og'irlik (0..1)
PRIOR = {
    "telegram": {8: .55, 9: .8, 12: .6, 13: .75, 18: .6, 19: .7, 20: 1.0, 21: .9},
    "instagram": {9: .5, 12: .8, 13: .75, 18: .7, 19: .9, 20: 1.0, 21: .95},
    "youtube": {12: .5, 15: .6, 17: .85, 18: .95, 19: 1.0, 20: .9},
}
PER_DAY_CAP = {"telegram": 3, "instagram": 2, "youtube": 1}
MIN_GAP_MIN = {"telegram": 90, "instagram": 180, "youtube": 360}


def _history(business, platform: str, days: int = 120):
    from apps.metrics.analytics import latest_metrics_qs
    rows = latest_metrics_qs(business.pk, since=timezone.now() - timedelta(days=days)).exclude(er=None).filter(post__platform=platform)
    return list(rows.select_related("post"))


def suggest_times(business, platform: str, *, now: datetime | None = None, days_ahead: int = 7, n: int = 6, exclude_item: int | None = None) -> list[dict]:
    from apps.content.models import ContentItem
    now = now or timezone.now()
    rows = _history(business, platform)
    by_wh, by_h, by_w = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        t = local(r.post.published_at)
        by_wh[(t.weekday(), t.hour)].append(r.er)
        by_h[t.hour].append(r.er)
        by_w[t.weekday()].append(r.er)
    avg = lambda v: sum(v) / len(v)
    top = max([avg(v) for v in by_h.values() if len(v) >= 2] or [0]) or 0
    prior = PRIOR.get(platform, PRIOR["telegram"])
    # band vaqtlar: shu platformaga rejalashtirilgan boshqa kontent
    q = ContentItem.objects.filter(business=business, targets__account__platform=platform, scheduled_at__gte=now - timedelta(hours=6),
                                   scheduled_at__lte=now + timedelta(days=days_ahead + 1)).exclude(status="published").distinct()
    if exclude_item:
        q = q.exclude(pk=exclude_item)
    busy = sorted(local(i.scheduled_at) for i in q if i.scheduled_at)
    per_day = defaultdict(int)
    for b in busy:
        per_day[b.date()] += 1
    cands = []
    base = local(now)
    for d in range(days_ahead + 1):
        day = (base + timedelta(days=d)).date()
        for h in range(7, 24):
            slot = datetime(day.year, day.month, day.day, h, 0, tzinfo=tz())
            if slot < base + timedelta(minutes=45):
                continue
            wh, hh, ww = by_wh.get((slot.weekday(), h), []), by_h.get(h, []), by_w.get(slot.weekday(), [])
            if len(wh) >= 2:
                data, src, k = avg(wh), "shu hafta kuni va soat", len(wh)
            elif len(hh) >= 2:
                data, src, k = avg(hh), "shu soat", len(hh)
            else:
                data, src, k = None, None, 0
            p = prior.get(h, .15)
            if data is not None and top:
                score = .7 * min(1.0, data / top) + .3 * p
                reason = f"{src} bo'yicha o'rtacha ER {data:.1f}% ({k} ta post)"
            else:
                score = p * .85
                reason = "umumiy tavsiya (hali yetarli ma'lumot yo'q)"
            if ww and len(ww) >= 3 and data is None:
                score *= 1.0 + min(.1, (avg(ww) - avg([x for v in by_w.values() for x in v])) / 100)
            note = ""
            if any(abs((slot - b).total_seconds()) < MIN_GAP_MIN.get(platform, 90) * 60 for b in busy):
                continue   # shu platformada yaqin vaqtda boshqa kontent bor
            if per_day[slot.date()] >= PER_DAY_CAP.get(platform, 2):
                score *= .55
                note = "bu kuni allaqachon ko'p post"
            elif per_day[slot.date()]:
                note = f"bu kuni {per_day[slot.date()]} ta post bor"
            cands.append({"at": slot, "score": score, "reason": reason, "note": note, "samples": k})
    cands.sort(key=lambda c: -c["score"])
    out, used_day = [], defaultdict(int)
    for c in cands:
        if used_day[c["at"].date()] >= 2:
            continue
        used_day[c["at"].date()] += 1
        a = c["at"]
        out.append({"value": a.strftime("%Y-%m-%dT%H:%M"), "label": f"{WEEKDAYS[a.weekday()]}, {a.day} {UZ_MON[a.month]} · {a:%H:%M}",
                    "score": round(c["score"] * 100), "reason": c["reason"], "note": c["note"], "data_based": c["samples"] > 0})
        if len(out) >= n:
            break
    return out


def best_common_slot(business, platforms, *, exclude_item: int | None = None, now: datetime | None = None):
    """Barcha tanlangan platformalar uchun umumiy eng yaxshi BO'SH vaqt (rejalashtirilgan kontent hisobga olinadi).
    Qaytaradi: {"at": aware datetime, "label", "reason"} yoki None."""
    plats = [p for p in dict.fromkeys(platforms) if p]
    if not plats:
        return None
    per = {p: {s["value"]: s for s in suggest_times(business, p, now=now, days_ahead=10, n=60, exclude_item=exclude_item)} for p in plats}
    common = set.intersection(*(set(v) for v in per.values())) if per else set()
    if common:
        best = max(common, key=lambda v: sum(per[p][v]["score"] for p in plats))
        info = per[plats[0]][best]
    else:   # umumiy bo'sh vaqt yo'q — birinchi platformaning eng yaxshisi
        best = max(per[plats[0]], key=lambda v: per[plats[0]][v]["score"], default=None)
        if best is None:
            return None
        info = per[plats[0]][best]
    at = datetime.strptime(best, "%Y-%m-%dT%H:%M").replace(tzinfo=tz())
    return {"at": at, "label": info["label"], "reason": info["reason"], "note": info["note"]}


def insights_brief(business, platform: str | None = None) -> str:
    """AI so'roviga qo'shiladigan qisqa tahlil: eng yaxshi postlar, turlar, vaqtlar, hashtaglar (o'zbekcha)."""
    from apps.metrics import analytics as an
    parts = []
    try:
        for r in an.top_posts(business, 3, days=90, platform=platform):
            t = (r.post.text or "").strip().replace("\n", " ")[:110]
            parts.append(f"- TOP post ({r.post.media_type}, ER {r.er:.1f}%): «{t}»")
        bt = [x for x in an.by_type(business, 90, platform=platform) if x["avg_er"] is not None][:2]
        if bt:
            parts.append("- Eng samarali turlar: " + ", ".join(f"{x['type']} (ER {x['avg_er']:.1f}%)" for x in bt))
        bw = an.best_times(business, 90, platform=platform)
        if bw["hour"]:
            parts.append("- Eng yaxshi soatlar: " + ", ".join(f"{h:02d}:00" for h, _, _ in bw["hour"][:3]))
        tags = an.hashtag_stats(business, 90, 5, platform=platform)
        if tags:
            parts.append("- Samarali hashtaglar: " + ", ".join(t["tag"] for t in tags))
    except Exception:  # noqa: BLE001 — tahlil bo'lmasa ham AI ishlayveradi
        pass
    return "\n".join(parts) if parts else "(hali yetarli statistika yo'q — umumiy SMM tajribasiga tayan)"
