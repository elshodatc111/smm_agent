from django.conf import settings
from django.db import models


class Report(models.Model):
    KINDS = [("weekly", "Haftalik"), ("monthly", "Oylik"), ("period", "Tanlangan davr"),
             ("competitors", "Raqobatchilar bilan solishtirish"), ("plan", "Kontent-plan"), ("ads", "Reklama natijasi")]
    STATUS = [("generating", "Tayyorlanmoqda"), ("ready", "Tayyor"), ("failed", "Xato"), ("awaiting_approval", "Tasdiq kutilmoqda"), ("sent", "Yuborildi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="reports")
    kind = models.CharField(max_length=12, choices=KINDS)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS, default="generating")
    pdf = models.FileField(upload_to="reports/%Y/%m/", null=True, blank=True)
    xlsx = models.FileField(upload_to="reports/%Y/%m/", null=True, blank=True)
    summary_text = models.TextField(blank=True)      # mijozga botda yuboriladigan matn
    data = models.JSONField(default=dict, blank=True)
    with_client_logo = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    share_token = models.CharField(max_length=40, blank=True, db_index=True)   # mijozga yuboriladigan maxfiy havola
    share_expires = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReportSchedule(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="report_schedules")
    kind = models.CharField(max_length=12, choices=Report.KINDS[:2])
    weekday = models.PositiveSmallIntegerField(default=0)   # haftalik: 0=dushanba
    day_of_month = models.PositiveSmallIntegerField(default=1)  # oylik
    hour = models.PositiveSmallIntegerField(default=9)
    auto_send = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    last_run_key = models.CharField(max_length=30, blank=True)
