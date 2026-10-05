from apps.jobs.queue import JobContext, register_handler


@register_handler("ads_scan", "system")
def ads_scan(ctx: JobContext):
    from apps.businesses.models import Business
    from . import services
    n = 0
    for b in Business.objects.filter(archived_at__isnull=True):
        n += len(services.find_candidates(b))
    return {"recommendations": n}
