from django.db import transaction

from apps.core.audit import audit

from .models import Business, BrandProfile

TEMPLATES = {
    "oquv_markaz": {"name": "O'quv markaz", "config": {
        "key_metrics": ["lead", "royxatga_olish", "kurs_tolovi"],
        "content_types": ["reels", "natijalar", "o'qituvchi tanishuvi", "aksiya", "savol-javob"],
        "seasonality": "Sentabr va yanvarda qabul avjida; yozda pasayish",
        "defaults": {"ctr": 0.012, "click_to_lead": 0.06, "cpm": 25000},
        "advice": "Lead va ro'yxatga olishga e'tibor; ota-onalar uchun ishonch kontenti."}},
    "shaxsiy_blog": {"name": "Shaxsiy blog (dizayner / SMM)", "config": {
        "key_metrics": ["obunachi_osishi", "saqlash", "ulashish", "murojaat"],
        "content_types": ["portfolio ishlar", "oldin-keyin", "jarayon (reels)", "maslahat va dars", "keys (natija bilan)", "shaxsiy hikoya", "mijoz sharhi", "narx va xizmatlar"],
        "seasonality": "Yangi yil, Navro'z, bayramlar oldidan buyurtma ko'payadi; yozda biroz pasayish",
        "defaults": {"ctr": 0.012, "click_to_lead": 0.05, "cpm": 22000},
        "advice": "Shaxsiy brend: ko'proq jarayon va natija ko'rsating, foydali maslahat bering, har 3-4 postdan birida xizmat taklif qiling."}},
    "kiyim_dokoni": {"name": "Kiyim do'koni", "config": {
        "key_metrics": ["saqlash", "ulashish", "katalog_kliklari"],
        "content_types": ["lookbook", "yangi kolleksiya", "aksiya", "mijoz sharhi", "reels (kiyib ko'rish)"],
        "seasonality": "Mavsum almashuvi, Navro'z, Ramazon/Hayit, Yangi yil",
        "defaults": {"ctr": 0.015, "click_to_lead": 0.08, "cpm": 20000},
        "advice": "Vizual kontent va aksiya; mahsulot katalogiga yo'naltirish."}},
    "kompyuter_xizmatlari": {"name": "Kompyuter xizmatlari", "config": {
        "key_metrics": ["murojaat", "javob_tezligi", "ishonch"],
        "content_types": ["ish jarayoni", "maslahat", "oldin-keyin", "B2B keys", "narx ro'yxati"],
        "seasonality": "Hisobot davrlari (B2B), o'quv yili boshi (B2C)",
        "defaults": {"ctr": 0.01, "click_to_lead": 0.05, "cpm": 22000},
        "advice": "Xizmat ishonchi va tez javob; B2B va B2C alohida xabarlar."}},
}


def ensure_templates():
    from .models import BusinessTemplate
    for key, t in TEMPLATES.items():
        BusinessTemplate.objects.get_or_create(key=key, defaults={"name": t["name"], "config": t["config"]})


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
