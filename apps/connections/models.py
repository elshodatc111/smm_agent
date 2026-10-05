from django.db import models

from apps.core import crypto

PLATFORMS = [("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube")]


class TelegramBot(models.Model):
    """Bitta bot bir nechta kanalga ulana oladi."""
    name = models.CharField(max_length=80)
    username = models.CharField(max_length=80, blank=True)
    token_enc = models.TextField()
    active = models.BooleanField(default=True)
    is_agency_bot = models.BooleanField(default=False)  # mijoz kabineti boti

    def token(self) -> str:
        return crypto.decrypt(self.token_enc)

    def set_token(self, t: str) -> None:
        self.token_enc = crypto.encrypt(t.strip())

    def __str__(self):
        return self.name


class TelegramSession(models.Model):
    """Telethon (faqat o'qish) sessiyasi; shifrlangan; xavfsizlik hisoblagichlari bilan."""
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=30, blank=True)
    session_enc = models.TextField(blank=True)  # StringSession, Fernet bilan
    active = models.BooleanField(default=True)
    requests_today = models.PositiveIntegerField(default=0)
    day = models.DateField(null=True, blank=True)
    consecutive_errors = models.PositiveSmallIntegerField(default=0)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    last_request_at = models.DateTimeField(null=True, blank=True)

    def string_session(self) -> str:
        return crypto.decrypt(self.session_enc) if self.session_enc else ""

    def __str__(self):
        return self.name


class SocialAccount(models.Model):
    STATUS = [("active", "Faol"), ("paused", "To'xtatilgan"), ("error", "Xato"),
              ("token_expiring", "Token tugayapti"), ("archived", "Arxiv")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="accounts")
    platform = models.CharField(max_length=12, choices=PLATFORMS)
    external_id = models.CharField(max_length=120, blank=True)
    handle = models.CharField(max_length=120, blank=True)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=16, choices=STATUS, default="active")
    credentials_enc = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    bot = models.ForeignKey(TelegramBot, null=True, blank=True, on_delete=models.SET_NULL, related_name="channels")
    tg_session = models.ForeignKey(TelegramSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="channels")
    autopublish_enabled = models.BooleanField(default=True)  # kill switch
    collect_schedule = models.JSONField(null=True, blank=True)  # override
    last_collect_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=400, blank=True)
    history_imported = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["business", "platform"])]

    def __str__(self):
        return f"{self.get_platform_display()}: {self.name}"

    def credentials(self) -> dict:
        return crypto.decrypt_json(self.credentials_enc) or {}

    def set_credentials(self, data: dict) -> None:
        self.credentials_enc = crypto.encrypt_json(data)

    def merge_credentials(self, **kw) -> None:
        d = self.credentials()
        d.update(kw)
        self.set_credentials(d)
        self.save(update_fields=["credentials_enc"])

    @property
    def is_collectable(self) -> bool:
        return self.status in ("active", "token_expiring") and self.archived_at is None


class Competitor(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="competitors")
    platform = models.CharField(max_length=12, choices=PLATFORMS)
    handle = models.CharField(max_length=160)
    name = models.CharField(max_length=160, blank=True)
    url = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    last_light_at = models.DateTimeField(null=True, blank=True)
    last_full_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("business", "platform", "handle")]

    def __str__(self):
        return f"{self.name or self.handle} ({self.platform})"
