from apps.jobs.queue import JobContext, register_handler


@register_handler("story_publish", "publish")
def story_publish(ctx: JobContext):
    from . import services
    return {"result": services.publish_target(ctx.payload["target_id"])}


@register_handler("story_stats", "publish")
def story_stats(ctx: JobContext):
    from . import services
    return {"ok": services.refresh_stats(ctx.payload["target_id"])}


@register_handler("story_prepare", "publish")
def story_prepare(ctx: JobContext):
    from . import services
    pl = ctx.payload
    return {"result": services.prepare_story(pl["story_id"], pl.get("accounts", []), pl.get("when"))}


@register_handler("story_check_accounts", "publish")
def story_check_accounts(ctx: JobContext):
    from . import services
    return {"checked": services.check_all(ctx.payload.get("ids")), "stuck": services.watchdog()}
