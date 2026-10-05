from apps.jobs.queue import JobContext, register_handler


@register_handler("notify_telegram", "system")
def notify_telegram(ctx: JobContext):
    from apps.core.models import Notification
    from .bot import make_api
    n = Notification.objects.get(pk=ctx.payload["notification_id"])
    u = n.user
    api = make_api()
    if not (u and u.telegram_id and api):
        return {"skipped": True}
    api.send(u.telegram_id, f"{n.title}\n{n.body}"[:3900])
    n.telegram_sent = True
    n.save(update_fields=["telegram_sent"])
    return {"sent": True}


@register_handler("client_publish_notice", "system")
def client_publish_notice(ctx: JobContext):
    from .client_notify import send_for_target
    return send_for_target(ctx.payload["target_id"])
