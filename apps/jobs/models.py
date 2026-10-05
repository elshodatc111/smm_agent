from django.db import models


class Job(models.Model):
    STATUS = [("pending", "Kutmoqda"), ("running", "Bajarilmoqda"), ("done", "Tayyor"),
              ("failed", "Xato"), ("cancelled", "Bekor qilingan")]
    type = models.CharField(max_length=60, db_index=True)
    queue = models.CharField(max_length=12, default="system")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    priority = models.PositiveSmallIntegerField(default=5)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    run_at = models.DateTimeField(db_index=True)
    locked_by = models.CharField(max_length=60, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    dedupe_key = models.CharField(max_length=200, blank=True, db_index=True)
    business_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "queue", "run_at", "priority"])]

    def __str__(self):
        return f"{self.type}#{self.pk}[{self.status}]"


class JobLog(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="logs")
    at = models.DateTimeField(auto_now_add=True)
    message = models.TextField()


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=60, unique=True)
    beat_at = models.DateTimeField()
    info = models.JSONField(default=dict)
