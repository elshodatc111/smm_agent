from django.conf import settings
from django.db import models


class SystemSetting(models.Model):
    """key/value sozlama. Sirlar Fernet bilan shifrlanadi (value_enc)."""
    key = models.CharField(max_length=120)
    scope = models.CharField(max_length=20, default="global")  # global|business|connection
    scope_id = models.PositiveBigIntegerField(default=0)
    value = models.JSONField(null=True, blank=True)
    value_enc = models.TextField(blank=True, default="")
    is_secret = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("key", "scope", "scope_id")]


class AuditLog(models.Model):
    """Faqat qo'shiladi: o'zgartirib/o'chirib bo'lmaydi."""
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    business_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=80, db_index=True)
    target = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    def save(self, *a, **kw):
        if self.pk:
            raise PermissionError("Audit jurnali o'zgartirilmaydi")
        super().save(*a, **kw)

    def delete(self, *a, **kw):
        raise PermissionError("Audit jurnali o'chirilmaydi")


class Notification(models.Model):
    SEVERITY = [("info", "Ma'lumot"), ("warn", "Ogohlantirish"), ("critical", "Jiddiy")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    business_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    type = models.CharField(max_length=60, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITY, default="info")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=200, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    telegram_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]


class NotificationPref(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_prefs")
    type = models.CharField(max_length=60)
    web = models.BooleanField(default=True)
    telegram = models.BooleanField(default=False)

    class Meta:
        unique_together = [("user", "type")]
