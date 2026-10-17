"""Onlayn kanal: mustaqil bo'lim (biznesga bog'liq emas). Har bir loyiha = bitta Telegram bot + yopiq guruh(lar) + tariflar + leadlar."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core import crypto

LEAD_STATUS = [("new", "Yangi"), ("phone", "Telefon berdi"), ("interested", "Qiziqdi"), ("waiting", "To'lov kutilmoqda"),
               ("sold", "Sotildi"), ("lost", "Rad etdi")]


class OnlineProject(models.Model):
    STATUS = [("draft", "Tayyorlanmoqda"), ("active", "Faol"), ("paused", "To'xtatilgan")]
    name = models.CharField(max_length=120)
    status = models.CharField(max_length=8, choices=STATUS, default="draft")
    token_enc = models.TextField(blank=True)
    bot_id = models.BigIntegerField(null=True, blank=True)
    bot_username = models.CharField(max_length=80, blank=True)
    bot_title = models.CharField(max_length=80, blank=True)          # Telegramdagi bot nomi (Bot API: setMyName)
    about = models.CharField(max_length=120, blank=True)             # qisqa tavsif (profil sahifasida)
    description = models.TextField(blank=True, max_length=512)       # /start dan oldin ko'rinadigan matn
    avatar = models.FileField(upload_to="online/avatars/", blank=True)
    commands = models.JSONField(default=list, blank=True)            # [{"command":"start","description":"..."}]
    brief = models.TextField(blank=True)                             # AI uchun loyiha haqida qisqa ma'lumot
    # to'lov
    card_number = models.CharField(max_length=32, blank=True)
    card_holder = models.CharField(max_length=80, blank=True)
    card_bank = models.CharField(max_length=60, blank=True)
    escalate_min = models.PositiveSmallIntegerField(default=15)      # shuncha daqiqada javob bo'lmasa zaxira adminlarga yuboriladi
    # leadlar va arxiv guruhlari
    leads_chat_id = models.BigIntegerField(null=True, blank=True)
    leads_chat_title = models.CharField(max_length=120, blank=True)
    pay_chat_id = models.BigIntegerField(null=True, blank=True)      # bo'sh bo'lsa to'lov arxivi leadlar guruhiga tushadi
    pay_chat_title = models.CharField(max_length=120, blank=True)
    repost_days = models.PositiveSmallIntegerField(default=30)
    ask_phone = models.BooleanField(default=True)                    # /start dan keyin telefon so'rash
    # obuna
    remind_days = models.CharField(max_length=20, default="3,1")
    # AI mentor
    ai_enabled = models.BooleanField(default=True)
    ai_instructions = models.TextField(blank=True)
    ai_free_daily = models.PositiveSmallIntegerField(default=3)      # obunasizlarga kuniga savol
    ai_sub_daily = models.PositiveSmallIntegerField(default=50)      # obunachilarga kuniga savol (0 = cheksiz)
    # bot oqimi (qoralama va joriy) — JSON: {"screens": {...}, "texts": {...}}
    flow = models.JSONField(default=dict, blank=True)
    flow_draft = models.JSONField(null=True, blank=True)
    flow_published_at = models.DateTimeField(null=True, blank=True)
    # texnik
    update_offset = models.BigIntegerField(default=0)
    last_check = models.JSONField(default=list, blank=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def token(self) -> str:
        return crypto.decrypt(self.token_enc) if self.token_enc else ""

    def set_token(self, t: str) -> None:
        self.token_enc = crypto.encrypt(t.strip()) if t else ""

    @property
    def pay_target(self):
        return self.pay_chat_id or self.leads_chat_id

    @property
    def bot_link(self):
        return f"https://t.me/{self.bot_username}" if self.bot_username else ""

    def __str__(self):
        return self.name


class ProjectAdmin(models.Model):
    """Loyihaga mas'ul shaxs (Telegram orqali to'lovni tasdiqlaydi, botda statistika ko'radi)."""
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="admins")
    tg_id = models.BigIntegerField()
    name = models.CharField(max_length=80, blank=True)
    is_primary = models.BooleanField(default=True)       # birinchi bo'lib shunga yuboriladi; boshqalari — zaxira
    can_stats = models.BooleanField(default=True)
    awaiting = models.JSONField(default=dict, blank=True)    # {"type": "reject", "payment": id}

    class Meta:
        unique_together = [("project", "tg_id")]
        ordering = ["-is_primary", "id"]


class ProjectGroup(models.Model):
    """Obunachilar kiritiladigan yopiq guruh/kanal."""
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="groups")
    chat_id = models.BigIntegerField()
    title = models.CharField(max_length=120, blank=True)
    ok = models.BooleanField(default=False)
    note = models.CharField(max_length=200, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("project", "chat_id")]
        ordering = ["id"]


class Tariff(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="tariffs")
    name = models.CharField(max_length=80)
    days = models.PositiveIntegerField(default=30)
    price = models.PositiveBigIntegerField(default=0)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort", "id"]

    def __str__(self):
        return f"{self.name} — {self.price}"


class OnlineMedia(models.Model):
    """Bot ekranlariga biriktiriladigan rasm/video (Telegram file_id keshlanadi)."""
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="online/media/%Y/%m/")
    kind = models.CharField(max_length=6, default="photo")     # photo | video
    tg_file_id = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Lead(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="leads")
    tg_id = models.BigIntegerField()
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    username = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=10, blank=True)
    is_premium = models.BooleanField(default=False)
    bio = models.CharField(max_length=300, blank=True)
    photo_file_id = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    phone_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=LEAD_STATUS, default="new")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    exempt = models.BooleanField(default=False)          # cheksiz / xodim: guruhdan chiqarilmaydi
    blocked = models.BooleanField(default=False)         # qora ro'yxat
    bot_blocked = models.BooleanField(default=False)     # foydalanuvchi botni to'xtatgan
    awaiting = models.JSONField(default=dict, blank=True)
    starts = models.PositiveIntegerField(default=1)
    ai_active = models.BooleanField(default=False)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)
    # leadlar guruhidagi post
    post_msg_id = models.BigIntegerField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    post_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("project", "tg_id")]
        ordering = ["-last_seen"]
        indexes = [models.Index(fields=["project", "status"])]

    @property
    def full_name(self):
        return (f"{self.first_name} {self.last_name}").strip() or self.username or str(self.tg_id)

    def __str__(self):
        return self.full_name


class LeadNote(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="notes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    text = models.TextField()
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Subscription(models.Model):
    STATUS = [("active", "Faol"), ("expired", "Tugagan"), ("cancelled", "Bekor qilingan")]
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="subs")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="subs")
    tariff = models.ForeignKey(Tariff, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    source = models.CharField(max_length=10, default="payment")      # payment | manual
    reminded = models.JSONField(default=list, blank=True)           # [3, 1] — yuborilgan eslatmalar
    removed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["project", "status", "ends_at"])]


class Payment(models.Model):
    STATUS = [("pending", "Kutilmoqda"), ("approved", "Tasdiqlandi"), ("rejected", "Rad etildi")]
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="payments")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="payments")
    tariff = models.ForeignKey(Tariff, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    amount = models.PositiveBigIntegerField(default=0)
    receipt_file_id = models.CharField(max_length=300, blank=True)
    receipt_uid = models.CharField(max_length=100, blank=True, db_index=True)
    duplicate = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    decided_by = models.CharField(max_length=80, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reject_reason = models.CharField(max_length=300, blank=True)
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    admin_msgs = models.JSONField(default=list, blank=True)         # [[chat_id, message_id], ...]
    escalated = models.BooleanField(default=False)
    archive_msg_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class KnowledgeDoc(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="docs")
    title = models.CharField(max_length=160)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class AiLog(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="ailogs")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    question = models.TextField()
    answer = models.TextField(blank=True)
    test = models.BooleanField(default=False)      # panelda sinov
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class FlowVersion(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="versions")
    data = models.JSONField()
    note = models.CharField(max_length=120, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class BotEvent(models.Model):
    project = models.ForeignKey(OnlineProject, on_delete=models.CASCADE, related_name="events")
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    kind = models.CharField(max_length=24)
    text = models.CharField(max_length=300)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["project", "kind"])]
