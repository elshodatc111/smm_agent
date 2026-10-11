from apps.core.notify import notify
from apps.jobs.queue import JobContext, register_handler

from . import services as gs


@register_handler("goals_snapshot", "system")
def goals_snapshot(ctx: JobContext):
    """Har kuni (va kun davomida yangilab): maqsad qiymatini yozadi, muddat/erishish holatini yopadi, ortda qolganda ogohlantiradi."""
    n = alerts = closed = 0
    today = gs.today_local()
    week = f"{today.isocalendar().year}-{today.isocalendar().week:02d}"
    for g in gs.active_goals():
        gs.snapshot(g, today)
        n += 1
        p = gs.compute(g, today=today)
        link = f"/maqsadlar/{g.pk}/"
        if p.state == "achieved":
            gs.close_goal(g, "achieved")
            notify("goal.achieved", f"Maqsadga erishildi: {g}", p.message, business_id=g.business_id, severity="info", link=link, dedupe_key=f"goal-ok:{g.pk}")
            closed += 1
        elif p.state == "missed":
            gs.close_goal(g, "missed")
            notify("goal.missed", f"Maqsad muddati tugadi: {g}", p.message, business_id=g.business_id, severity="warning", link=link, dedupe_key=f"goal-miss:{g.pk}")
            closed += 1
        elif p.state in ("behind", "at_risk") and p.days_elapsed >= 14 and g.last_alert_week != week:
            notify("goal.behind", f"Maqsad ortda qolmoqda: {g}", p.message, business_id=g.business_id, severity="warning", link=link, dedupe_key=f"goal-beh:{g.pk}:{week}", dedupe_minutes=60 * 24 * 6)
            g.last_alert_week = week
            g.save(update_fields=["last_alert_week"])
            alerts += 1
    return {"snapshots": n, "alerts": alerts, "closed": closed}
