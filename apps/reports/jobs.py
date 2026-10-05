
from django.utils import timezone

from apps.core.notify import notify
from apps.core.utils import local
from apps.jobs.queue import JobContext, enqueue, register_handler

from .generator import default_period, generate_report
from .models import Report, ReportSchedule


@register_handler("report_generate", "system")
def report_generate(ctx: JobContext):
    r = Report.objects.get(pk=ctx.payload["report_id"])
    generate_report(r)
    notify("report.ready", f"Hisobot tayyor: {r.business.name}", r.get_kind_display(), business_id=r.business_id, link=f"/hisobotlar/{r.pk}/")
    if ctx.payload.get("deliver"):
        if ctx.payload.get("requires_approval"):
            r.status = "awaiting_approval"
            r.save(update_fields=["status"])
        else:
            enqueue("report_deliver", {"report_id": r.pk}, queue="system", business_id=r.business_id)
    return {"report_id": r.pk}


@register_handler("report_deliver", "system")
def report_deliver(ctx: JobContext):
    from apps.tgbot.bot import deliver_report
    r = Report.objects.get(pk=ctx.payload["report_id"])
    n = deliver_report(r)
    r.status, r.delivered_at = "sent", timezone.now()
    r.save(update_fields=["status", "delivered_at"])
    return {"recipients": n}


@register_handler("report_schedules", "system")
def report_schedules(ctx: JobContext):
    now = local(timezone.now())
    n = 0
    for s in ReportSchedule.objects.filter(active=True):
        due = (s.kind == "weekly" and now.weekday() == s.weekday) or (s.kind == "monthly" and now.day == s.day_of_month)
        key = f"{s.kind}:{now.date()}"
        if due and now.hour >= s.hour and s.last_run_key != key:
            ps, pe = default_period(s.kind, now.date())
            r = Report.objects.create(business=s.business, kind=s.kind, period_start=ps, period_end=pe)
            enqueue("report_generate", {"report_id": r.pk, "deliver": s.auto_send, "requires_approval": s.requires_approval},
                    queue="system", business_id=s.business_id)
            s.last_run_key = key
            s.save(update_fields=["last_run_key"])
            n += 1
    return {"scheduled": n}
