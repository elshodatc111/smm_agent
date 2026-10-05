from datetime import date

from apps.jobs.queue import JobContext, register_handler


@register_handler("why_worked", "ai")
def why_worked_job(ctx: JobContext):
    from apps.metrics.models import Post
    from . import services
    ins = services.why_worked(Post.objects.get(pk=ctx.payload["post_id"]))
    return {"insight_id": ins.pk}


@register_handler("classify_comments", "ai")
def classify_comments_job(ctx: JobContext):
    from apps.metrics.models import Comment
    from . import services
    n = 0
    for c in Comment.objects.filter(business_id=ctx.payload["business_id"], sentiment="")[:30]:
        services.classify_comment(c)
        n += 1
    return {"classified": n}


@register_handler("ai_plan", "ai")
def plan_job(ctx: JobContext):
    from apps.businesses.models import Business
    from . import services
    b = Business.objects.get(pk=ctx.payload["business_id"])
    p = services.monthly_plan(b, ctx.payload["platform"], date.fromisoformat(ctx.payload["month"]))
    return {"plan_id": p.pk}


@register_handler("ai_script", "ai")
def script_job(ctx: JobContext):
    from apps.businesses.models import Business
    from . import services
    b = Business.objects.get(pk=ctx.payload["business_id"])
    s = services.generate_script(b, ctx.payload["brief"], ctx.payload.get("fmt", "reel"), ctx.payload.get("variants", 2))
    return {"script_id": s.pk}


@register_handler("ai_brand_profile", "ai")
def brand_job(ctx: JobContext):
    from apps.businesses.models import Business
    from . import services
    bp = services.generate_brand_profile(Business.objects.get(pk=ctx.payload["business_id"]))
    return {"brand_version": bp.version}


@register_handler("post_summary", "ai")
def post_summary_job(ctx: JobContext):
    from apps.metrics import post_summary
    return post_summary.run(ctx.payload["post_id"], ctx.payload.get("window", "24h"))


@register_handler("ideas_daily", "ai")
def ideas_daily_job(ctx: JobContext):
    from apps.businesses.models import Business
    from . import ideas
    b = Business.objects.get(pk=ctx.payload["business_id"])
    return {"created": len(ideas.ensure_daily(b))}
