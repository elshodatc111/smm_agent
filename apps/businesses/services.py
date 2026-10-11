from django.db import transaction

from apps.core.audit import audit

from .models import Business, BrandProfile

def ensure_templates():
    """Tizim biznes turlarini yaratadi; mavjudlarini admin tahririni buzmasdan to'ldiradi."""
    from .models import BusinessTemplate
    from .types_data import TYPES
    for key, t in TYPES.items():
        obj, created = BusinessTemplate.objects.get_or_create(key=key, defaults={
            "name": t["name"], "config": t["config"], "profile_fields": t["fields"], "topics": t["topics"], "is_system": True, "sort": t.get("sort", 50)})
        if not created:
            upd = []
            if not obj.profile_fields:
                obj.profile_fields = t["fields"]; upd.append("profile_fields")
            if not obj.topics and t["topics"]:
                obj.topics = t["topics"]; upd.append("topics")
            if not obj.is_system:
                obj.is_system = True; upd.append("is_system")
            if not obj.config:
                obj.config = t["config"]; upd.append("config")
            if upd:
                obj.save(update_fields=upd)


@transaction.atomic
def save_brand_version(business: Business, content: str, *, user=None, structured=None,
                       status="draft", note="", ai=False) -> BrandProfile:
    last = business.brand_profiles.order_by("-version").first()
    bp = BrandProfile.objects.create(business=business, version=(last.version + 1) if last else 1,
                                     content=content, structured=structured or {}, status=status,
                                     note=note, created_by=user, generated_by_ai=ai)
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
