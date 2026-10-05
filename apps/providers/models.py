from django.db import models


class ProviderState(models.Model):
    name = models.CharField(max_length=60, unique=True)
    enabled = models.BooleanField(default=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    credits_remaining = models.FloatField(null=True, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    avg_latency_ms = models.FloatField(null=True, blank=True)


class ProviderUsageLog(models.Model):
    provider = models.CharField(max_length=60, db_index=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    kind = models.CharField(max_length=30, blank=True)  # profile|posts|...|upload
    target = models.CharField(max_length=200, blank=True)
    units = models.FloatField(default=0)               # kvota birligi yoki kredit
    unit_type = models.CharField(max_length=20, default="quota_units")
    ok = models.BooleanField(default=True)
    from_cache = models.BooleanField(default=False)
    latency_ms = models.FloatField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [models.Index(fields=["provider", "at"])]


class FailoverEvent(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    platform = models.CharField(max_length=12, blank=True)
    kind = models.CharField(max_length=30, blank=True)
    from_provider = models.CharField(max_length=60)
    to_provider = models.CharField(max_length=60, blank=True)
    reason = models.CharField(max_length=200)

    class Meta:
        ordering = ["-at"]


class ResponseCache(models.Model):
    key = models.CharField(max_length=200, unique=True)
    data = models.JSONField()
    fetched_at = models.DateTimeField(auto_now_add=True)
