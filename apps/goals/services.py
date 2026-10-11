"""Maqsadlar: qiymatni o'lchash, progress/tezlik hisobi, nishon takliflari. Raqamlarni KOD hisoblaydi."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.core.utils import local, tz

from .models import Goal, GoalRevision, GoalSnapshot

DEFAULT_DAYS = 90

STATE_UZ = {
    "achieved": ("Bajarildi", "ok"), "on_track": ("Reja bo'yicha", "ok"), "at_risk": ("Xavf ostida", "warn"),
    "behind": ("Ortda qolmoqda", "bad"), "starting": ("Boshlanmoqda", "blue"), "missed": ("Bajarilmadi", "bad"),
    "cancelled": ("Bekor qilindi", ""),
}
UNIT = {"followers": "ta", "views": "ta", "posts": "ta", "er": "%"}


def today_local() -> date:
    return local(timezone.now()).date()


def _start_dt(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz())


def fmt(v, metric: str) -> str:
    if v is None:
        return "—"
    if metric == "er":
        return f"{v:.1f}%"
    return f"{int(round(v)):,}".replace(",", " ")


# ----------------------------------------------------------------------------- o'lchash
def measure(account, metric: str, start: date, *, as_of: date | None = None) -> float | None:
    """Maqsad boshlangandan (start) buyongi joriy qiymat. Ma'lumot yo'q bo'lsa None."""
    from apps.metrics.analytics import latest_metrics_qs
    from apps.metrics.models import AccountMetrics, DailyStat, Post
    if metric == "followers":
        am = AccountMetrics.objects.filter(account=account, followers__isnull=False).order_by("-taken_at").first()
        if am:
            return float(am.followers)
        ds = DailyStat.objects.filter(account=account, followers__isnull=False).order_by("-day").first()
        return float(ds.followers) if ds else None
    since = _start_dt(start)
    if metric == "posts":
        return float(Post.objects.filter(account=account, published_at__gte=since).count())
    if metric == "views":
        rows = latest_metrics_qs(account_id=account.pk, since=since)
        return float(sum(r.views or 0 for r in rows))
    if metric == "er":
        rows = [r.er for r in latest_metrics_qs(account_id=account.pk, since=since) if r.er is not None]
        return (sum(rows) / len(rows) * 100) if rows else None
    return None


def baseline_for(account, metric: str, today: date | None = None) -> float:
    """Maqsad qo'yilayotgan paytdagi boshlang'ich qiymat."""
    today = today or today_local()
    if metric == "followers":
        return measure(account, "followers", today) or 0.0
    if metric == "er":
        from apps.metrics.analytics import latest_metrics_qs
        rows = [r.er for r in latest_metrics_qs(account_id=account.pk, since=_start_dt(today - timedelta(days=60))) if r.er is not None]
        return (sum(rows) / len(rows) * 100) if rows else 0.0
    return 0.0


# ----------------------------------------------------------------------------- progress
@dataclass
class Progress:
    current: float | None
    baseline: float
    target: float
    pct: float
    remaining: float
    days_total: int
    days_elapsed: int
    days_left: int
    expected_pct: float
    projected: float | None
    rate_per_day: float
    required_per_day: float
    state: str
    confidence: str
    message: str
    data_points: int

    @property
    def state_label(self):
        return STATE_UZ.get(self.state, (self.state, ""))[0]

    @property
    def state_cls(self):
        return STATE_UZ.get(self.state, ("", ""))[1]

    @property
    def ring_cls(self):
        return {"achieved": "ok", "on_track": "ok", "at_risk": "warn", "behind": "bad", "missed": "bad"}.get(self.state, "")


def compute(goal: Goal, *, today: date | None = None, current: float | None = None) -> Progress:
    today = today or today_local()
    total = max(1, (goal.end_date - goal.start_date).days)
    elapsed = max(0, min(total, (today - goal.start_date).days))
    left = max(0, (goal.end_date - today).days)
    if current is None:
        current = goal.final_value if goal.status != "active" and goal.final_value is not None else measure(goal.account, goal.metric, goal.start_date)
    gap = goal.target - goal.baseline
    pts = goal.snapshots.filter(value__isnull=False).count()
    if current is None:
        return Progress(None, goal.baseline, goal.target, 0, gap, total, elapsed, left, round(elapsed / total * 100), None, 0, 0,
                        "starting", "low", "Hozircha ma'lumot yo'q: ulanish ma'lumot yig'ishi bilan hisoblanadi.", pts)
    done = current - goal.baseline
    pct = (done / gap * 100) if gap > 0 else (100.0 if current >= goal.target else 0.0)
    pct = max(0.0, pct)
    remaining = max(0.0, goal.target - current)
    exp_pct = elapsed / total * 100
    rate = done / elapsed if elapsed > 0 else 0.0
    if goal.metric == "er":                         # ER — o'rtacha ko'rsatkich, chiziqli o'smaydi
        projected = current
        req = 0.0
    else:
        projected = goal.baseline + rate * total if elapsed > 0 else None
        req = remaining / left if left > 0 else remaining
    conf = "high" if (elapsed >= 21 and pts >= 5) else ("medium" if elapsed >= 7 else "low")
    if goal.status == "cancelled":
        state = "cancelled"
    elif goal.status == "achieved" or (goal.status == "active" and current >= goal.target):
        state = "achieved"
    elif goal.status == "missed" or (today > goal.end_date):
        state = "missed"
    elif elapsed < 3:
        state = "starting"
    elif pct >= exp_pct - 5:
        state = "on_track"
    elif projected is not None and gap > 0 and (projected - goal.baseline) >= 0.8 * gap:
        state = "at_risk"
    else:
        state = "behind"
    msg = _message(goal, state, current, remaining, left, rate, req, projected, conf)
    return Progress(current, goal.baseline, goal.target, round(pct, 1), remaining, total, elapsed, left, round(exp_pct, 1),
                    projected, rate, req, state, conf, msg, pts)


def _message(goal, state, current, remaining, left, rate, req, projected, conf) -> str:
    m = goal.metric
    unit = UNIT[m]
    if state == "achieved":
        return f"Maqsadga erishildi: {fmt(current, m)} {unit if m != 'er' else ''}.".strip()
    if state == "missed":
        return f"Muddat tugadi: {fmt(current, m)} / {fmt(goal.target, m)}. Keyingi maqsadni sozlang."
    if state == "starting":
        return "Maqsad endi boshlandi: tezlik hisobi uchun kamida 3 kun ma'lumot kerak."
    if m == "er":
        return f"Hozirgi o'rtacha ER {fmt(current, m)}, maqsad {fmt(goal.target, m)}. Eng yaxshi ishlagan kontent turlarini ko'paytiring."
    if state == "on_track":
        s = f"Reja bo'yicha ketmoqdasiz. Qolgan: {fmt(remaining, m)} {unit}"
    else:
        s = f"Maqsad uchun har kuni o'rtacha {req:.1f} {unit} kerak, hozirgi tezlik esa {rate:.1f}/kun. Qolgan: {fmt(remaining, m)} {unit}"
    if projected is not None and conf != "low":
        s += f". Shu tezlikda muddat oxirida taxminan {fmt(projected, m)} bo'ladi"
    if conf == "low":
        s += " (ma'lumot kam: baho taxminiy)"
    return s + "."


def milestones(goal: Goal, weeks: int | None = None) -> list[dict]:
    """Haftalik chegaralar: reja (chiziqli) va haqiqiy qiymat (snapshotlardan)."""
    total = max(1, (goal.end_date - goal.start_date).days)
    n = weeks or max(1, math.ceil(total / 7))
    snaps = {s.day: s.value for s in goal.snapshots.all()}
    days = sorted(snaps)
    today = today_local()
    out = []
    for i in range(1, n + 1):
        d = min(goal.end_date, goal.start_date + timedelta(days=7 * i))
        plan = goal.baseline + (goal.target - goal.baseline) * ((d - goal.start_date).days / total)
        actual = None
        if d <= today:
            prior = [x for x in days if x <= d]
            actual = snaps[prior[-1]] if prior else None
        status = None
        if actual is not None:
            status = "ok" if actual >= plan * 0.97 else ("warn" if actual >= plan * 0.85 else "bad")
        out.append({"week": i, "date": d, "plan": plan, "actual": actual, "status": status, "future": d > today})
    return out


def chart_series(goal: Goal) -> dict:
    ms = milestones(goal)
    labels = [goal.start_date.strftime("%d.%m")] + [m["date"].strftime("%d.%m") for m in ms]
    plan = [round(goal.baseline, 1)] + [round(m["plan"], 1) for m in ms]
    first = goal.snapshots.order_by("day").first()
    actual = [round(first.value, 1) if first and first.day <= goal.start_date + timedelta(days=1) and first.value is not None else round(goal.baseline, 1)] + \
             [round(m["actual"], 1) if m["actual"] is not None else None for m in ms]
    return {"labels": labels, "series": [{"name": "Reja", "data": plan}, {"name": "Haqiqiy", "data": actual}]}


# ----------------------------------------------------------------------------- nishon takliflari
def _round_nice(v: float, metric: str) -> float:
    if metric == "er":
        return round(v, 1)
    if v < 50:
        return float(math.ceil(v / 5) * 5)
    if v < 500:
        return float(math.ceil(v / 10) * 10)
    if v < 5000:
        return float(math.ceil(v / 50) * 50)
    return float(math.ceil(v / 500) * 500)


def _growth_30d(account) -> tuple[float | None, int]:
    """So'nggi 30 kunda obunachi o'sishi (kuzatuv soni bilan)."""
    from apps.metrics.models import AccountMetrics
    now = timezone.now()
    qs = AccountMetrics.objects.filter(account=account, followers__isnull=False, taken_at__gte=now - timedelta(days=30)).order_by("taken_at")
    n = qs.count()
    if n < 2:
        return None, n
    a, b = qs.first(), qs.last()
    days = max(1, (b.taken_at - a.taken_at).days)
    return (b.followers - a.followers) / days * 30, n


def suggest_targets(account, metric: str, days: int = DEFAULT_DAYS) -> dict:
    """Uch variant: ehtiyotkor / o'rtacha / shiddatli. Taxminiy: o'z o'sishingiz va akkaunt hajmiga qarab."""
    from apps.metrics.analytics import latest_metrics_qs
    from apps.metrics.models import Post
    base = baseline_for(account, metric)
    notes: list[str] = []
    if metric == "followers":
        g30, npts = _growth_30d(account)
        size = base
        if size < 100:
            m = (1.4, 2.0, 3.2); add = (10, 25, 60)
        elif size < 1000:
            m = (1.25, 1.6, 2.2); add = (40, 100, 250)
        elif size < 10000:
            m = (1.12, 1.3, 1.6); add = (150, 400, 1000)
        else:
            m = (1.06, 1.15, 1.3); add = (600, 1500, 4000)
        vals = [max(base * m[i], base + add[i]) for i in range(3)]
        if g30 is not None and g30 > 0:
            k = days / 30
            vals = [max(vals[0], base + g30 * k * 0.9), max(vals[1], base + g30 * k * 1.4), max(vals[2], base + g30 * k * 2.2)]
            notes.append(f"So'nggi 30 kunda o'sish ≈ {g30:+.0f} ta; variantlar shunga moslandi.")
        else:
            notes.append("O'sish tarixi yetarli emas: variantlar akkaunt hajmiga qarab taxminiy olindi.")
        conf = "medium" if (g30 is not None and npts >= 5) else "low"
    elif metric == "posts":
        since = timezone.now() - timedelta(days=30)
        n30 = Post.objects.filter(account=account, published_at__gte=since).count()
        per_week = n30 / 4.3
        weeks = days / 7
        vals = [max(per_week * weeks * 1.0, weeks * 2), max(per_week * weeks * 1.4, weeks * 3), max(per_week * weeks * 2.0, weeks * 5)]
        notes.append(f"Hozirgi ritm ≈ haftasiga {per_week:.1f} ta post.")
        conf = "medium" if n30 >= 4 else "low"
    elif metric == "views":
        rows = list(latest_metrics_qs(account_id=account.pk, since=timezone.now() - timedelta(days=45)))
        vs = [r.views or 0 for r in rows]
        avg_views = (sum(vs) / len(vs)) if vs else 0
        per_week = len(rows) / 6.4
        weeks = days / 7
        est = avg_views * max(per_week, 1.5) * weeks
        if est <= 0:
            est = 30 * 2 * weeks
            notes.append("Ko'rishlar tarixi yo'q: o'rtacha qiymatlar taxminiy qo'yildi.")
        else:
            notes.append(f"Hozir post boshiga o'rtacha ≈ {avg_views:.0f} ko'rish, haftasiga ≈ {per_week:.1f} post.")
        vals = [est * 0.9, est * 1.4, est * 2.2]
        conf = "medium" if len(rows) >= 6 else "low"
    elif metric == "er":
        b = base if base > 0 else 4.0
        vals = [b * 1.10, b * 1.25, b * 1.5]
        notes.append("ER o'rtacha ko'rsatkich: o'sish nisbiy olinadi.")
        conf = "medium" if base > 0 else "low"
    else:
        vals = [0, 0, 0]
        conf = "low"
    labels = [("Ehtiyotkor", "Sekin, lekin aniq erishiladigan"), ("O'rtacha", "Muntazam ishlasangiz real"), ("Shiddatli", "Katta kuch va reklamani talab qiladi")]
    opts = []
    for (lab, hint), v in zip(labels, vals):
        v = _round_nice(v, metric)
        if metric != "er":
            v = max(v, base + (1 if metric == "followers" else 1))
        opts.append({"label": lab, "hint": hint, "value": v, "gain": v - base})
    return {"baseline": base, "options": opts, "notes": notes, "confidence": conf}


# ----------------------------------------------------------------------------- amallar
def create_goal(*, account, metric: str, target: float, end_date: date | None = None, title: str = "", note: str = "", user=None,
                start_date: date | None = None) -> Goal:
    start = start_date or today_local()
    end = end_date or (start + timedelta(days=DEFAULT_DAYS))
    base = baseline_for(account, metric, start)
    g = Goal.objects.create(business_id=account.business_id, account=account, metric=metric, target=float(target), baseline=base, start_date=start,
                            end_date=end, title=title, note=note, created_by=user)
    snapshot(g)
    return g


def update_goal(goal: Goal, *, target: float | None = None, end_date: date | None = None, note: str | None = None, title: str | None = None,
                reason: str = "", user=None) -> Goal:
    old_t, old_e = goal.target, goal.end_date
    changed = False
    if target is not None and float(target) != goal.target:
        goal.target = float(target); changed = True
    if end_date is not None and end_date != goal.end_date:
        goal.end_date = end_date; changed = True
    if note is not None:
        goal.note = note
    if title is not None:
        goal.title = title
    goal.save()
    if changed:
        GoalRevision.objects.create(goal=goal, user=user, old_target=old_t, new_target=goal.target, old_end=old_e, new_end=goal.end_date, reason=reason[:300])
    return goal


def close_goal(goal: Goal, status: str, user=None) -> Goal:
    assert status in ("achieved", "missed", "cancelled")
    cur = measure(goal.account, goal.metric, goal.start_date)
    goal.status = status
    goal.final_value = cur
    goal.closed_at = timezone.now()
    goal.save()
    return goal


def snapshot(goal: Goal, day: date | None = None) -> GoalSnapshot | None:
    day = day or today_local()
    cur = measure(goal.account, goal.metric, goal.start_date)
    if cur is None:
        return None
    s, _ = GoalSnapshot.objects.update_or_create(goal=goal, day=day, defaults={"value": cur})
    return s


def active_goals(business_ids=None):
    qs = Goal.objects.filter(status="active").select_related("account", "business")
    if business_ids is not None:
        qs = qs.filter(business_id__in=business_ids)
    return qs


def summary_for(business, limit: int = 6) -> list[dict]:
    out = []
    for g in Goal.objects.filter(business=business, status="active").select_related("account")[:limit]:
        out.append({"goal": g, "p": compute(g)})
    return out


def accounts_without_goal(business) -> list:
    have = set(Goal.objects.filter(business=business, status="active").values_list("account_id", flat=True))
    return [a for a in business.accounts.filter(archived_at__isnull=True) if a.pk not in have]
