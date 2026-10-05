from django.conf import settings
from django.db import models


class MediaFile(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="media_files")
    file = models.FileField(upload_to="media_analysis/%Y/%m/")
    original_name = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=8, default="video")  # video|image
    sha256 = models.CharField(max_length=64, db_index=True)
    size = models.BigIntegerField(default=0)
    status = models.CharField(max_length=10, default="pending")  # pending|running|done|failed
    post = models.ForeignKey("metrics.Post", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    job_id = models.PositiveBigIntegerField(null=True, blank=True)


class MediaAnalysis(models.Model):
    media = models.ForeignKey(MediaFile, on_delete=models.CASCADE, related_name="analyses")
    sha256 = models.CharField(max_length=64, db_index=True)
    technical = models.JSONField(default=dict)
    transcript = models.JSONField(null=True, blank=True)
    ai = models.JSONField(null=True, blank=True)
    degraded = models.BooleanField(default=False)
    step_results = models.JSONField(default=dict)
    took_sec = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
