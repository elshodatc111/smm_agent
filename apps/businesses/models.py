from django.conf import settings
from django.db import models


class BusinessTemplate(models.Model):
    """Faoliyat turi andozasi: metrikalar, kontent turlari, tavsiya mantig'i."""
    key = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    config = models.JSONField(default=dict)  # key_metrics, content_types, seasonality, ctr/conv defaults, notes

    def __str__(self):
        return self.name


class Business(models.Model):
    GOALS = [("followers", "Obuna"), ("lead", "Murojaat"), ("sales", "Sotuv"), ("views", "Ko'rish")]
    name = models.CharField(max_length=120)
    logo = models.ImageField(upload_to="logos/", null=True, blank=True)
    template = models.ForeignKey(BusinessTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    industry = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    languages = models.CharField(max_length=60, default="uz")
    description = models.TextField(blank=True)
    products = models.TextField(blank=True)
    price_range = models.CharField(max_length=120, blank=True)
    audience = models.TextField(blank=True)
    main_goal = models.CharField(max_length=20, choices=GOALS, default="followers")
    monthly_ad_budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="UZS")
    avg_check = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    lead_to_sale = models.FloatField(default=0.2)
    margin = models.FloatField(null=True, blank=True)
    contact_info = models.TextField(blank=True)
    facts = models.JSONField(default=dict, blank=True)  # Content Rules «haqiqiylik»: phones, prices, address, discounts
    autopublish_enabled = models.BooleanField(default=True)  # kill switch
    client_approval_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    brand_update_suggested = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def active_brand(self):
        return self.brand_profiles.filter(status="approved").order_by("-version").first()


class BrandProfile(models.Model):
    """Brend xotirasi: versiyalanadi."""
    STATUS = [("draft", "Qoralama"), ("approved", "Tasdiqlangan")]
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="brand_profiles")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    content = models.TextField()  # system prompt
    structured = models.JSONField(default=dict, blank=True)  # tone, usp, banned_words, hashtags, cta, pillars
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    generated_by_ai = models.BooleanField(default=False)

    class Meta:
        unique_together = [("business", "version")]
        ordering = ["-version"]
