from django.conf import settings
from django.db import models


class AdCampaign(models.Model):
    STATUS = [("plan", "Loyiha"), ("running", "Ishlayapti"), ("done", "Tugagan"), ("cancelled", "Bekor qilingan")]
    PLATFORMS = [("telegram_ads", "Telegram Ads"), ("meta", "Instagram (Meta)"), ("youtube", "YouTube")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="ad_campaigns")
    name = models.CharField(max_length=200)
    platform = models.CharField(max_length=14, choices=PLATFORMS)
    objective = models.CharField(max_length=20, default="lead")
    budget = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    daily_budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="plan")
    post = models.ForeignKey("metrics.Post", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    plan = models.JSONField(default=dict, blank=True)       # auditoriya, joylashuv, matn variantlari, to'xtatish qoidasi
    forecast = models.JSONField(default=dict, blank=True)   # uch stsenariy
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AdRecommendation(models.Model):
    STATUS = [("new", "Yangi"), ("accepted", "Qabul qilindi"), ("dismissed", "Rad etildi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="ad_recs")
    post = models.ForeignKey("metrics.Post", on_delete=models.CASCADE, related_name="+")
    score = models.FloatField()
    reasons = models.JSONField(default=list)
    best_time = models.CharField(max_length=120, blank=True)
    budget_share = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]


class AdResult(models.Model):
    campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name="results")
    date = models.DateField()
    spend = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    leads = models.IntegerField(default=0)
    sales = models.IntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        unique_together = [("campaign", "date")]
        ordering = ["date"]
