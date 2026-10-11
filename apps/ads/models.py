from django.conf import settings
from django.db import models


class AdProposal(models.Model):
    """Reklama taklifi: qaysi post/video reklamaga arziydi va qanday yoqish kerak. Reklama bu tizimda YOQILMAYDI — targetolog uchun taklif."""
    OBJECTIVES = [("subscribers", "Yangi obunachilar"), ("views", "Ko'rishlarni oshirish"), ("leads", "Murojaat / lid olish"),
                  ("sales", "Sotuvni oshirish"), ("profile", "Profilga tashrif / trafik")]
    STATUS = [("new", "Yangi"), ("sent", "Targetologga berildi"), ("used", "Ishlatildi"), ("dismissed", "Rad etildi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="ad_proposals")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="ad_proposals")
    platform = models.CharField(max_length=12)                      # telegram | instagram
    objective = models.CharField(max_length=12, choices=OBJECTIVES)
    note = models.CharField(max_length=300, blank=True)
    evidence = models.JSONField(default=dict, blank=True)           # kod hisoblagan raqamlar
    result = models.JSONField(default=dict, blank=True)             # taklif (tuzilgan)
    confidence = models.CharField(max_length=8, default="low")      # low | medium | high
    source = models.CharField(max_length=8, default="rules")        # ai | rules
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
