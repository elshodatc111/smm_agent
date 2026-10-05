from apps.jobs.queue import JobContext, register_handler

from .models import MediaFile
from .pipeline import analyze_media


@register_handler("media_analyze", "media")
def media_analyze(ctx: JobContext):
    m = MediaFile.objects.get(pk=ctx.payload["media_file_id"])
    m.status = "running"
    m.save(update_fields=["status"])
    try:
        a = analyze_media(m, progress=ctx.report_progress)
    except Exception:
        m.status = "failed"
        m.save(update_fields=["status"])
        raise
    m.status = "done"
    m.save(update_fields=["status"])
    return {"analysis_id": a.pk, "degraded": a.degraded, "took_sec": a.took_sec}
