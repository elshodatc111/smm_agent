from django.conf import settings
from django.db import models

from apps.core import crypto

PROVIDERS = [("gemini", "Gemini"), ("groq", "Groq"), ("openrouter", "OpenRouter"), ("claude", "Claude"), ("openai", "OpenAI")]


class AIKey(models.Model):
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    alias = models.CharField(max_length=60)
    key_enc = models.TextField()
    enabled = models.BooleanField(default=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    fail_streak = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    rpm_limit = models.PositiveIntegerField(null=True, blank=True)
    rpd_limit = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("provider", "alias")]

    def secret(self) -> str:
        return crypto.decrypt(self.key_enc)

    def set_secret(self, v: str) -> None:
        self.key_enc = crypto.encrypt(v.strip())


class AIUsageLog(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    provider = models.CharField(max_length=20, db_index=True)
    model = models.CharField(max_length=80, blank=True)
    key_alias = models.CharField(max_length=60, blank=True)
    task = models.CharField(max_length=30, blank=True)
    business_id = models.PositiveBigIntegerField(null=True, blank=True)
    ok = models.BooleanField(default=True)
    error = models.CharField(max_length=300, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=5, default=0)
    latency_ms = models.FloatField(null=True, blank=True)


class AICache(models.Model):
    key = models.CharField(max_length=64, unique=True)
    result = models.JSONField()
    expires_at = models.DateTimeField(db_index=True)


class AIGeneration(models.Model):
    """Barcha AI natijalari tarixi (qaysi model/provayder, brend versiyasi)."""
    business = models.ForeignKey("businesses.Business", null=True, blank=True, on_delete=models.SET_NULL, related_name="generations")
    task = models.CharField(max_length=30)
    kind = models.CharField(max_length=40, blank=True)  # plan|script|caption|...
    prompt = models.TextField(blank=True)
    text = models.TextField(blank=True)
    data = models.JSONField(null=True, blank=True)
    provider = models.CharField(max_length=20, blank=True)
    model = models.CharField(max_length=80, blank=True)
    brand_version = models.PositiveIntegerField(null=True, blank=True)
    lang_ok = models.BooleanField(default=True)
    from_cache = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
