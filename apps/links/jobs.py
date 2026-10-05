from apps.jobs.queue import JobContext, register_handler

from . import services


@register_handler("link_sync", "system")
def link_sync(ctx: JobContext):
    return services.sync_clicks()
