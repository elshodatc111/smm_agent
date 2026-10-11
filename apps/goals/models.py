from django.conf import settings
from django.db import models


class Goal(models.Model):
    """Har bir ijtimoiy tarmoq akkaunti uchun (odatda 3 oylik) maqsad. Natija ma'lumotlardan avtomatik hisoblanadi."""
    METRICS = [("followers", "Obunachilar soni"), ("views", "Yangi kontent ko'rishlari"), ("posts", "Chiqarilgan postlar soni"),
               ("er", "O'rtacha faollik (ER, %)"), ("leads", "Lidlar soni")]
    STATUS = [("active", "Faol"), ("achieved", "Bajarildi"), ("missed", "Bajarilmadi"), ("cancelled", "Bekor qilindi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="goals")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="goals")
    metric = models.CharField(max_length=12, choices=METRICS)
    title = models.CharField(max_length=160, blank=True)
    note = models.TextField(blank=True)
    baseline = models.FloatField(default=0)           # boshlang'ich qiymat (maqsad qo'yilgan paytdagi)
    target = models.FloatField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default="active", db_index=True)
    last_alert_week = models.CharField(max_length=10, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    final_value = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "status"])]

    def __str__(self):
        return self.title or f"{self.account} — {self.get_metric_display()}"


class GoalSnapshot(models.Model):
    """Kunlik qiymat tarixi (grafik uchun)."""
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="snapshots")
    day = models.DateField()
    value = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = [("goal", "day")]
        ordering = ["day"]


class GoalRevision(models.Model):
    """Maqsad o'zgartirilgan har bir holat: kim, qachon, nimadan nimaga."""
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE, related_name="revisions")
    at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    old_target = models.FloatField(null=True, blank=True)
    new_target = models.FloatField(null=True, blank=True)
    old_end = models.DateField(null=True, blank=True)
    new_end = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-at"]
