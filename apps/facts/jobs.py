from apps.core.notify import notify
from apps.jobs.queue import JobContext, register_handler

from . import engine


@register_handler("facts_refresh", "system")
def facts_refresh(ctx: JobContext):
    """Kunlik: manbalarni yangilash va takliflar tayyorlash. payload.business_id bo'lsa faqat o'sha biznes."""
    from apps.businesses.models import Business
    bid = (ctx.payload or {}).get("business_id")
    b = Business.objects.filter(pk=bid).first() if bid else None
    res = engine.refresh_all(b)
    for biz_id, n in res.get("per_business", {}).items():
        if n:
            notify("facts.new", f"{n} ta yangi fakt/yangilik taklifi", "Faktlar va yangiliklar bo'limida ko'ring.", business_id=biz_id,
                   link="/faktlar/", dedupe_key=f"facts-new:{biz_id}", dedupe_minutes=60 * 12)
    return {k: v for k, v in res.items() if k != "per_business"}
