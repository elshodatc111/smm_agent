from django.conf import settings
from django.db import models


class ContentPlan(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="plans")
    platform = models.CharField(max_length=12)
    month = models.DateField()  # oyning 1-kuni
    entries = models.JSONField(default=list)  # [{date, format, topic, hook, cta, goal, assignee}]
    summary = models.TextField(blank=True)
    generation = models.ForeignKey("ai_router.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    loaded_to_calendar = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month", "-created_at"]


class Script(models.Model):
    FORMATS = [("reel", "Reels/Shorts"), ("long", "Uzun YouTube video"), ("ad", "Reklama roligi"),
               ("podcast", "Podkast"), ("stories", "Stories ketma-ketligi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="scripts")
    title = models.CharField(max_length=200)
    fmt = models.CharField(max_length=10, choices=FORMATS, default="reel")
    brief = models.TextField(blank=True)
    body = models.JSONField(default=dict)  # hook, scenes[], cta, duration, props, variants
    raw_text = models.TextField(blank=True)  # qo'lda yozilgan/yuklangan
    generation = models.ForeignKey("ai_router.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ScriptAnalysis(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE, related_name="analyses")
    score = models.PositiveSmallIntegerField(default=0)
    data = models.JSONField(default=dict)  # criteria{hook,structure,pace,cta,brand,sales}, fixes[]
    generation = models.ForeignKey("ai_router.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Hook(models.Model):
    SOURCES = [("own", "O'z post"), ("competitor", "Raqobatchi"), ("manual", "Qo'lda")]
    STATUS = [("suggested", "Taklif"), ("saved", "Saqlangan"), ("rejected", "Rad etilgan")]
    business = models.ForeignKey("businesses.Business", null=True, blank=True, on_delete=models.CASCADE, related_name="hooks")
    text = models.TextField()
    fmt = models.CharField(max_length=12, blank=True)
    topic = models.CharField(max_length=120, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    result = models.JSONField(default=dict, blank=True)  # views, er
    tags = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=12, choices=SOURCES, default="manual")
    status = models.CharField(max_length=10, choices=STATUS, default="saved")
    post = models.ForeignKey("metrics.Post", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PostInsight(models.Model):
    post = models.ForeignKey("metrics.Post", on_delete=models.CASCADE, related_name="insights")
    numbers = models.JSONField(default=dict)   # kod hisoblagan raqamli asos
    verdict = models.CharField(max_length=20, blank=True)  # winner|average|weak
    text = models.TextField(blank=True)        # AI izohi
    data = models.JSONField(null=True, blank=True)  # reasons[], repeat[], change[]
    generation = models.ForeignKey("ai_router.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Idea(models.Model):
    """G'oyalar banki: raqobatchi va o'z tahlili asosida AI tavsiya qilgan g'oya + shu g'oya uchun ssenariy."""
    STATUS = [("new", "Yangi"), ("saved", "Saqlangan"), ("used", "Ishlatilgan"), ("rejected", "Rad etilgan")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="ideas")
    title = models.CharField(max_length=200)
    platform = models.CharField(max_length=12, blank=True)
    fmt = models.CharField(max_length=12, blank=True)       # post|reel|short|story|carousel|video
    angle = models.TextField(blank=True)                    # g'oyaning mohiyati
    hook = models.CharField(max_length=300, blank=True)
    why = models.TextField(blank=True)                      # nega bu g'oya (tahlil asosi)
    source = models.CharField(max_length=20, default="auto")  # auto|competitor|own|manual
    source_ref = models.JSONField(default=dict, blank=True)   # {"competitor": "...", "post": "...", "views": 1234}
    script = models.JSONField(default=dict, blank=True)       # ssenariy (script_text bilan ko'rsatiladi)
    script_text = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="new")
    day = models.DateField(db_index=True)                     # qaysi kun uchun yaratilgan
    content_item = models.ForeignKey("content.ContentItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-day", "-created_at"]
