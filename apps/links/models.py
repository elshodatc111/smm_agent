from django.db import models


class ShortLink(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="links")
    slug = models.SlugField(max_length=40, unique=True)
    target_url = models.URLField(max_length=1000)
    utm = models.JSONField(default=dict, blank=True)
    content_item = models.ForeignKey("content.ContentItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="links")
    campaign = models.ForeignKey("ads.AdCampaign", null=True, blank=True, on_delete=models.SET_NULL, related_name="links")
    note = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    synced = models.BooleanField(default=False)
    sync_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class LinkClick(models.Model):
    link = models.ForeignKey(ShortLink, on_delete=models.CASCADE, related_name="clicks")
    remote_id = models.BigIntegerField(unique=True)
    clicked_at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=80, blank=True)
    device = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=4, blank=True)


class WorkerStatus(models.Model):
    checked_at = models.DateTimeField(auto_now=True)
    ok = models.BooleanField(default=False)
    message = models.CharField(max_length=300, blank=True)
    clicks_today = models.IntegerField(default=0)
    version = models.CharField(max_length=20, blank=True)
    last_remote_id = models.BigIntegerField(default=0)
