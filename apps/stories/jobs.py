from apps.jobs.queue import JobContext, register_handler


@register_handler("story_publish", "publish")
def story_publish(ctx: JobContext):
    from . import services
    return {"result": services.publish_target(ctx.payload["target_id"])}


@register_handler("story_stats", "publish")
def story_stats(ctx: JobContext):
    from . import services
    return {"ok": services.refresh_stats(ctx.payload["target_id"])}
