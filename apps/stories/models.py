"""Telegram Stories: mustaqil bo'lim (biznesga bog'liq emas). Akkauntlar, story, har akkaunt uchun natija, ko'rishlar tarixi."""
from django.conf import settings
from django.db import models

from apps.core import crypto

PERIODS = [(21600, "6 soat"), (43200, "12 soat"), (86400, "24 soat"), (172800, "48 soat")]
PRIVACY = [("all", "Hamma ko'radi"), ("contacts", "Faqat kontaktlar"), ("close", "Yaqin do'stlar")]


class StoryAccount(models.Model):
    STATUS = [("active", "Faol"), ("paused", "To'xtatilgan"), ("error", "Xato (qayta ulash kerak)")]
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=30, unique=True)
    username = models.CharField(max_length=80, blank=True)
    tg_user_id = models.BigIntegerField(null=True, blank=True)
    session_enc = models.TextField(blank=True)
    is_premium = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    last_error = models.CharField(max_length=300, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    can_post = models.BooleanField(null=True, blank=True)            # Telegram: hozir story qo'ya oladimi (oxirgi tekshiruv)
    remains = models.PositiveIntegerField(null=True, blank=True)     # Telegram aytgan qolgan story soni (bilinsa)
    checked_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def string_session(self) -> str:
        return crypto.decrypt(self.session_enc) if self.session_enc else ""

    def __str__(self):
        return f"{self.name} ({self.phone})"


class Story(models.Model):
    STATUS = [("draft", "Qoralama"), ("preparing", "Tayyorlanmoqda"), ("scheduled", "Rejalashtirilgan"), ("sending", "Yuborilmoqda"), ("done", "Hammasi joylandi"),
              ("partial", "Qisman joylandi"), ("failed", "Xato"), ("cancelled", "To'xtatilgan")]
    title = models.CharField(max_length=160)
    caption = models.TextField(blank=True)
    media = models.FileField(upload_to="stories/%Y/%m/")
    kind = models.CharField(max_length=6, default="photo")          # photo | video
    fit_mode = models.CharField(max_length=6, default="pad")        # pad | crop | orig
    period = models.PositiveIntegerField(default=86400)
    privacy = models.CharField(max_length=8, choices=PRIVACY, default="all")
    pinned = models.BooleanField(default=False)                      # profilda doimiy qoldirish
    noforwards = models.BooleanField(default=False)                  # ulashish/saqlashni taqiqlash
    link_url = models.URLField(max_length=300, blank=True)           # havola stikeri
    reaction = models.CharField(max_length=8, blank=True)            # «reaksiya» stikeri (emoji)
    geo_lat = models.FloatField(null=True, blank=True)               # joylashuv stikeri
    geo_lon = models.FloatField(null=True, blank=True)
    music_track = models.CharField(max_length=40, blank=True)         # Jamendo track id
    music_title = models.CharField(max_length=200, blank=True)
    music_artist = models.CharField(max_length=200, blank=True)
    music_license = models.CharField(max_length=300, blank=True)
    music_start = models.PositiveIntegerField(default=0)              # audio boshlanish soniyasi
    music_len = models.PositiveIntegerField(default=0)                # parcha uzunligi (10–30 s)
    music_src = models.URLField(max_length=600, blank=True)           # audio manzili (worker yuklab oladi)
    prepare_error = models.CharField(max_length=300, blank=True)
    music_video = models.FileField(upload_to="stories/music/%Y/%m/", blank=True)   # rasm/video + musiqa yig'ilgan mp4
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "scheduled_at"])]

    def __str__(self):
        return self.title


class StoryTarget(models.Model):
    STATUS = [("pending", "Kutilmoqda"), ("sending", "Yuborilmoqda"), ("sent", "Joylandi"), ("error", "Xato"), ("skipped", "O'tkazib yuborildi")]
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="targets")
    account = models.ForeignKey(StoryAccount, on_delete=models.CASCADE, related_name="targets")
    status = models.CharField(max_length=8, choices=STATUS, default="pending")
    run_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    tg_story_id = models.BigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=16, blank=True)         # premium|flood|limit|media|auth|other
    error = models.CharField(max_length=400, blank=True)
    views = models.PositiveIntegerField(default=0)
    forwards = models.PositiveIntegerField(default=0)
    reactions = models.PositiveIntegerField(default=0)
    stats_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["story", "account"], name="uniq_story_account")]


class StoryStat(models.Model):
    """Ko'rishlar tarixi: har yangilashda bitta qator (vaqt bo'yicha o'sishni ko'rsatish uchun)."""
    target = models.ForeignKey(StoryTarget, on_delete=models.CASCADE, related_name="snapshots")
    taken_at = models.DateTimeField(auto_now_add=True)
    views = models.PositiveIntegerField(default=0)
    forwards = models.PositiveIntegerField(default=0)
    reactions = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["taken_at", "id"]
