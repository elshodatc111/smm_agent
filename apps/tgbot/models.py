from django.conf import settings
from django.db import models

SECTIONS = [("kpi", "Asosiy ko'rsatkichlar"), ("report_weekly", "Haftalik hisobot"), ("report_monthly", "Oylik hisobot"),
            ("top_posts", "Eng yaxshi postlar"), ("content_plan", "Kontent-reja"),
            ("report_issue", "Muammo haqida xabar"), ("publish_notice", "Har bir nashr haqida xabar")]
ALL_SECTIONS = [s for s, _ in SECTIONS]


class ClientInvite(models.Model):
    code_hash = models.CharField(max_length=64, unique=True)
    business_ids = models.JSONField(default=list)
    label = models.CharField(max_length=120, blank=True)   # mijoz nomi (admin uchun)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class ClientBotUser(models.Model):
    tg_user_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=120, blank=True)
    business_ids = models.JSONField(default=list)
    sections = models.JSONField(default=dict)  # {"<business_id>": ["kpi", ...]}
    current_business = models.PositiveBigIntegerField(null=True, blank=True)
    awaiting = models.JSONField(default=dict, blank=True)  # {"type": "issue"|"changes", "item": id}
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def allowed(self, business_id: int) -> list[str]:
        return self.sections.get(str(business_id), ALL_SECTIONS)


class ClientNotice(models.Model):
    """Mijozga yuborilgan «post chiqdi» xabarlari (takror yuborilmasligi uchun)."""
    target_id = models.PositiveBigIntegerField(unique=True)
    business_id = models.PositiveBigIntegerField(db_index=True)
    sent_to = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
