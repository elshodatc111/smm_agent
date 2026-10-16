import hashlib

from django.conf import settings
from django.db import models

STATUSES = [("draft", "Qoralama"), ("pending_approval", "Tasdiqlash kutilmoqda"), ("approved", "Tasdiqlandi"),
            ("scheduled", "Rejalashtirildi"), ("publishing", "Nashr qilinmoqda"), ("published", "Chiqarildi"),
            ("failed", "Xato")]
MEDIA_TYPES = [("text", "Matn"), ("image", "Rasm"), ("video", "Video"), ("album", "Albom"), ("reel", "Reels"),
               ("short", "Shorts"), ("story", "Stories"), ("carousel", "Karusel")]


class ActiveItems(models.Manager):
    """Savatdagi (o'chirilgan) postlar oddiy so'rovlarda ko'rinmaydi."""
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class ContentItem(models.Model):
    objects = ActiveItems()
    all_objects = models.Manager()
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="content_items")
    title = models.CharField(max_length=200)
    text = models.TextField(blank=True)
    media_type = models.CharField(max_length=12, choices=MEDIA_TYPES, default="text")
    status = models.CharField(max_length=20, choices=STATUSES, default="draft", db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_items")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_hash = models.CharField(max_length=64, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    due_at = models.DateTimeField(null=True, blank=True)
    ai_draft = models.BooleanField(default=False)
    ai_draft_reviewed = models.BooleanField(default=False)
    client_approval = models.CharField(max_length=20, blank=True)  # '', approved, changes_requested
    client_comment = models.TextField(blank=True)
    rule_status = models.CharField(max_length=10, blank=True)  # pass|warn|block
    rule_override_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    rule_override_reason = models.CharField(max_length=300, blank=True)
    options = models.JSONField(default=dict, blank=True)  # youtube: title,tags,privacy; telegram: buttons...
    notes = models.TextField(blank=True)
    brief = models.TextField(blank=True)   # dizayner/kontent-maker uchun vazifa matni
    design_status = models.CharField(max_length=10, blank=True)  # ''|todo|doing|ready|revision
    plan = models.ForeignKey("studio.ContentPlan", null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    hook_idea = models.CharField(max_length=300, blank=True)
    cta = models.CharField(max_length=200, blank=True)
    goal = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["business", "status", "scheduled_at"])]
        ordering = ["scheduled_at", "-created_at"]

    def __str__(self):
        return self.title

    def content_hash(self) -> str:
        h = hashlib.sha256()
        h.update((self.text or "").encode())
        h.update(self.media_type.encode())
        for a in self.assets.order_by("position", "id"):
            h.update(a.sha256.encode())
        h.update(str(sorted(self.options.items())).encode())
        return h.hexdigest()

    @property
    def partial(self) -> bool:
        s = set(self.targets.values_list("status", flat=True))
        return "published" in s and bool(s - {"published"})


class ContentTarget(models.Model):
    STATUS = [("pending", "Kutmoqda"), ("publishing", "Nashr qilinmoqda"), ("published", "Chiqarildi"),
              ("failed", "Xato"), ("failed_retry", "Qayta urinish"), ("blocked", "To'sildi")]
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="targets")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="targets")
    status = models.CharField(max_length=14, choices=STATUS, default="pending")
    external_id = models.CharField(max_length=200, blank=True)
    url = models.CharField(max_length=400, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=400, blank=True)
    blocked_by_kill_switch = models.BooleanField(default=False)

    class Meta:
        unique_together = [("item", "account")]


class ContentAsset(models.Model):
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="assets")
    file = models.FileField(upload_to="assets/%Y/%m/")
    kind = models.CharField(max_length=10, default="image")  # image|video|audio|thumbnail
    original_name = models.CharField(max_length=200, blank=True)
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    cloud = models.ForeignKey("TempObject", null=True, blank=True, on_delete=models.SET_NULL, related_name="used_by")  # Cloudflare'dan tanlangan bo'lsa
    position = models.PositiveSmallIntegerField(default=0)   # karusel/albomdagi tartib
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]


class PublishAttempt(models.Model):
    target = models.ForeignKey(ContentTarget, on_delete=models.CASCADE, related_name="attempts")
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=10, default="started")  # started|success|failed
    error = models.TextField(blank=True)
    retryable = models.BooleanField(default=True)
    external_id = models.CharField(max_length=200, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    number = models.PositiveSmallIntegerField(default=1)


class RuleSetEntry(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="rule_entries")
    rule_id = models.CharField(max_length=60)
    enabled = models.BooleanField(default=True)
    severity_override = models.CharField(max_length=6, blank=True)
    params = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = [("business", "rule_id")]


class RuleCheckResult(models.Model):
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="rule_checks")
    platform = models.CharField(max_length=12, blank=True)
    status = models.CharField(max_length=6)
    problems = models.JSONField(default=list)
    checked_at = models.DateTimeField(auto_now_add=True)


class TempObject(models.Model):
    """Vaqtinchalik ochiq hosting (Worker KV yoki R2) obyektlari."""
    key = models.CharField(max_length=200, unique=True)
    backend = models.CharField(max_length=12, blank=True)  # worker_kv|r2|fake ('' = hali yuklanmagan)
    size = models.BigIntegerField(default=0)
    public_url = models.CharField(max_length=800, blank=True)
    status = models.CharField(max_length=10, default="uploaded")  # uploading(brauzerdan)|pending|uploaded|deleted|failed
    progress = models.PositiveSmallIntegerField(default=0)  # 0..100 — Cloudflare'ga yuklash foizi
    item = models.ForeignKey(ContentItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="temp_objects")
    created_at = models.DateTimeField(auto_now_add=True)
    delete_after = models.DateTimeField(null=True, blank=True)
    business = models.ForeignKey("businesses.Business", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    asset = models.ForeignKey("ContentAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="cloud_objects")
    filename = models.CharField(max_length=200, blank=True)
    content_type = models.CharField(max_length=60, blank=True)
    error = models.CharField(max_length=300, blank=True)
    tags = models.CharField(max_length=300, blank=True)  # vergul bilan: kutubxona tegi
    local_path = models.CharField(max_length=500, blank=True)  # qo'lda yuklangan fayl vaqtincha shu yerda turadi
    progress = models.PositiveSmallIntegerField(default=0)


class ItemComment(models.Model):
    """Post ichidagi xodimlar yozishmasi va vazifa holati o'zgarishlari."""
    KINDS = [("comment", "Izoh"), ("status", "Holat")]
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=8, choices=KINDS, default="comment")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PostTemplate(models.Model):
    """Qayta ishlatiladigan post shabloni. Matnda {sana}, {kun}, {biznes} o'zgaruvchilari ishlatiladi."""
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="post_templates")
    name = models.CharField(max_length=120)
    platform = models.CharField(max_length=12, blank=True)   # '' = hammasi
    media_type = models.CharField(max_length=12, default="text")
    title = models.CharField(max_length=200, blank=True)
    text = models.TextField(blank=True)
    brief = models.TextField(blank=True)
    options = models.JSONField(default=dict, blank=True)
    time_hint = models.CharField(max_length=5, blank=True)   # "10:00" — shablondan yaratganda odatiy vaqt
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    uses = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uses", "name"]
