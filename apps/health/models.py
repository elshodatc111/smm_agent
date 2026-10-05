from django.db import models


class HealthSnapshot(models.Model):
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    data = models.JSONField(default=dict)


class BackupRecord(models.Model):
    at = models.DateTimeField(auto_now_add=True)
    path = models.CharField(max_length=300)
    size = models.BigIntegerField(default=0)
    ok = models.BooleanField(default=True)
    note = models.CharField(max_length=300, blank=True)
