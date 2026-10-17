from django.db import transaction

from apps.core.audit import audit

from .models import Business, BrandProfile

def ensure_templates():
    """Tizim biznes turlarini yaratadi; mavjudlarini admin tahririni buzmasdan to'ldiradi."""
    from .models import BusinessTemplate
    from .types_data import TYPES
    for key, t in TYPES.items():
        obj, created = BusinessTemplate.objects.get_or_create(key=key, defaults={
            "name": t["name"], "config": t["config"], "profile_fields": t["fields"], "is_system": True, "sort": t.get("sort", 50)})
        if not created:
            upd = []
            if not obj.profile_fields:
                obj.profile_fields = t["fields"]; upd.append("profile_fields")
            if not obj.is_system:
                obj.is_system = True; upd.append("is_system")
            if not obj.config:
                obj.config = t["config"]; upd.append("config")
            if upd:
                obj.save(update_fields=upd)


@transaction.atomic
def save_brand_version(business: Business, content: str, *, user=None, structured=None,
                       status="approved", note="", ai=False) -> BrandProfile:
    last = business.brand_profiles.order_by("-version").first()
    bp = BrandProfile.objects.create(business=business, version=(last.version + 1) if last else 1,
                                     content=content, structured=structured or {}, status=status,
                                     note=note, created_by=user, generated_by_ai=ai)
    if status == "approved":
        Business.objects.filter(pk=business.pk).update(brand_update_suggested=False)
    audit("brand.version", user=user, business_id=business.pk, target=f"v{bp.version}")
    return bp


@transaction.atomic
def approve_brand(bp: BrandProfile, user) -> BrandProfile:
    bp.status = "approved"
    bp.save(update_fields=["status"])
    Business.objects.filter(pk=bp.business_id).update(brand_update_suggested=False)
    audit("brand.approved", user=user, business_id=bp.business_id, target=f"v{bp.version}")
    return bp


def restore_brand(bp: BrandProfile, user) -> BrandProfile:
    new = save_brand_version(bp.business, bp.content, user=user, structured=bp.structured,
                             status="approved", note=f"v{bp.version} ga qaytarildi")
    return new


BUSINESS_PROMPT_FIELDS = ("name", "industry", "region", "languages", "description", "products",
                          "price_range", "audience", "main_goal", "contact_info")


def business_changed(business: Business, old: dict) -> None:
    """Biznes ma'lumoti o'zgarsa «Brend xotirasini yangilash» taklifi."""
    if any(getattr(business, f) != old.get(f) for f in BUSINESS_PROMPT_FIELDS if f in old):
        Business.objects.filter(pk=business.pk).update(brand_update_suggested=True)


def purge_business(business) -> dict:
    """Biznesni va unga tegishli HAMMA ma'lumotni (postlar, metrikalar, maqsadlar, fayllar...) butunlay o'chiradi. Qaytarib bo'lmaydi."""
    import os

    from django.db import transaction
    from django.db.models import FileField
    files: list[str] = []

    def collect(obj):
        for f in obj._meta.get_fields():
            if isinstance(f, FileField):
                v = getattr(obj, f.name, None)
                if v:
                    try:
                        files.append(v.path)
                    except Exception:  # noqa: BLE001
                        pass
    from django.db.models.deletion import Collector
    from django.db import router
    col = Collector(using=router.db_for_write(type(business)))
    col.collect([business])
    for model, objs in col.data.items():
        if any(isinstance(f, FileField) for f in model._meta.get_fields()):
            for o in objs:
                collect(o)
    name, pk = business.name, business.pk
    with transaction.atomic():
        business.delete()
    removed = 0
    for p in files:
        try:
            os.remove(p)
            removed += 1
        except OSError:
            pass
    return {"name": name, "id": pk, "files_removed": removed}
