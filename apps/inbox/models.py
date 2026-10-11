"""Murojaatlar: operatorning Telegram akkauntiga mijozlar yozgan xabarlar, AI javob skripti va javoblar jurnali."""
from django.conf import settings
from django.db import models

from apps.core import crypto


class InboxAccount(models.Model):
    """Operatorga tegishli Telegram akkaunti (Telethon sessiyasi). Mijozga hech qachon birinchi bo'lib yozmaydi."""
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="inbox_accounts")
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="inbox_accounts")
    name = models.CharField(max_length=80)
    ai_name = models.CharField(max_length=40, blank=True)             # AI ismi (masalan: Alisa) — mijozga «Men AI Alisaman» deb tanishtiriladi
    phone = models.CharField(max_length=30, blank=True)
    tg_user_id = models.BigIntegerField(null=True, blank=True)       # akkaunt egasining Telegram ID'si
    session_enc = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    auto_reply = models.BooleanField(default=True)                   # AI avtomatik javobi
    wait_minutes = models.PositiveSmallIntegerField(default=15)      # operator javob bermasa, AI shundan keyin qo'shiladi
    ai_delay_seconds = models.PositiveSmallIntegerField(default=30)  # AI suhbatga qo'shilgach, keyingi savollarga shuncha soniyadan keyin javob beradi
    ai_session_minutes = models.PositiveSmallIntegerField(default=180)  # AI javobidan keyin shuncha daqiqa «AI rejimi»; undan keyin yana operator kutiladi
    hourly_limit = models.PositiveSmallIntegerField(default=30)      # soatiga maksimal AI javoblari (ban'dan himoya)
    last_error = models.CharField(max_length=300, blank=True)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def string_session(self) -> str:
        return crypto.decrypt(self.session_enc) if self.session_enc else ""

    def __str__(self):
        return self.name


class Conversation(models.Model):
    STATUS = [("open", "Ochiq"), ("closed", "Yopilgan")]
    account = models.ForeignKey(InboxAccount, on_delete=models.CASCADE, related_name="conversations")
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="conversations")
    peer_id = models.BigIntegerField()
    peer_name = models.CharField(max_length=160, blank=True)
    peer_username = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default="open")
    ai_enabled = models.BooleanField(default=True)                   # shu suhbatda AI javob berishi mumkinmi
    needs_human = models.BooleanField(default=False)                 # AI javob bera olmadi / operator kerak
    human_reason = models.CharField(max_length=200, blank=True)
    ai_disclosed = models.BooleanField(default=False)                # mijozga «men AI» deb aytilganmi
    handoff_notified = models.BooleanField(default=False)
    unread = models.BooleanField(default=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("account", "peer_id")]
        ordering = ["-last_message_at"]

    def __str__(self):
        return self.peer_name or self.peer_username or str(self.peer_id)


class Message(models.Model):
    DIRECTION = [("in", "Mijozdan"), ("out", "Mijozga")]
    SENDER = [("customer", "Mijoz"), ("operator", "Operator"), ("ai", "AI yordamchi")]
    STATE = [("received", "Qabul qilindi"), ("pending", "Yuborilmoqda"), ("sent", "Yuborildi"), ("failed", "Xato")]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTION)
    sender = models.CharField(max_length=10, choices=SENDER)
    text = models.TextField(blank=True)
    tg_msg_id = models.BigIntegerField(null=True, blank=True)
    state = models.CharField(max_length=10, choices=STATE, default="received")
    error = models.CharField(max_length=300, blank=True)
    by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]


class ScriptEntry(models.Model):
    """AI faqat shu skriptdan javob beradi. qa — savol-javob; rule — umumiy qoida (ohang, taqiq); handoff — operatorga uzatish belgilari."""
    KINDS = [("qa", "Savol-javob"), ("rule", "Umumiy qoida"), ("handoff", "Operatorga uzatish")]
    SOURCES = [("manual", "Qo'lda"), ("learned", "Yozishmadan o'rganilgan")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="script_entries")
    kind = models.CharField(max_length=8, choices=KINDS, default="qa")
    title = models.CharField(max_length=160)
    questions = models.TextField(blank=True)        # mijoz so'rashi mumkin bo'lgan savollar/kalit so'zlar (har qatorda bittadan)
    answer = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    source = models.CharField(max_length=8, choices=SOURCES, default="manual")
    uses = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "title"]


class ScriptGap(models.Model):
    """Skriptda javobi topilmagan mijoz savollari: operator javobi bilan skriptga qo'shiladi."""
    STATUS = [("new", "Yangi"), ("added", "Skriptga qo'shildi"), ("ignored", "Kerak emas")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="script_gaps")
    question = models.TextField()
    key = models.CharField(max_length=80, db_index=True)   # normallashgan kalit (takroriylarni sanash uchun)
    count = models.PositiveIntegerField(default=1)
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=8, choices=STATUS, default="new")
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-count", "-last_seen_at"]


class AIReplyLog(models.Model):
    """AI'ning har bir qarori jurnali: nima deb javob berdi, qaysi skript qatoridan, qaysi model."""
    DECISIONS = [("answered", "Javob berdi"), ("handoff", "Operatorga uzatdi"), ("skipped", "Javob bermadi"), ("failed", "Xato")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="ai_reply_logs")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="ai_logs")
    decision = models.CharField(max_length=10, choices=DECISIONS)
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    reason = models.CharField(max_length=300, blank=True)
    script_ids = models.JSONField(default=list, blank=True)
    provider = models.CharField(max_length=20, blank=True)
    model = models.CharField(max_length=80, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
