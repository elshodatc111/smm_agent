from django.db import models


class FactSource(models.Model):
    """Tasdiqlangan manbalar katalogi (butun dunyo). Faqat shu manbalardan olingan ma'lumot taklifga kiradi."""
    TIER = [("A", "A — rasmiy / birlamchi manba"), ("B", "B — nufuzli nashr"), ("C", "C — o'zim qo'shgan")]
    name = models.CharField(max_length=120)
    url = models.CharField(max_length=300)                  # sayt bosh sahifasi (ko'rsatish uchun)
    feed_url = models.CharField(max_length=400)             # RSS / Atom manzili
    tier = models.CharField(max_length=1, choices=TIER, default="B")
    language = models.CharField(max_length=5, default="en")
    domains = models.JSONField(default=list, blank=True)    # ["design","smm","tech", biznes_turi_kaliti, ...]
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_ok = models.BooleanField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tier", "name"]
        unique_together = [("feed_url",)]

    def __str__(self):
        return self.name


class FactTopic(models.Model):
    """Biznes (va tarmoq) bo'yicha yo'nalish: nimadan fakt/yangilik kerak."""
    KIND = [("fact", "Qiziqarli fakt"), ("news", "Yangilik"), ("tip", "Foydali ma'lumot")]
    PLATFORMS = [("telegram", "Telegram"), ("instagram", "Instagram"), ("youtube", "YouTube")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="fact_topics")
    platform = models.CharField(max_length=12, choices=PLATFORMS)
    title = models.CharField(max_length=160)                # o'zbekcha nom
    keywords = models.JSONField(default=list, blank=True)   # inglizcha kalit so'zlar (manbalarda qidirish uchun)
    kinds = models.JSONField(default=list, blank=True)      # ["fact","news","tip"]
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["business", "platform", "title"]


class FactItem(models.Model):
    """Manbadan yig'ilgan material (faqat qisqa parcha va havola saqlanadi)."""
    source = models.ForeignKey(FactSource, on_delete=models.CASCADE, related_name="items")
    url = models.CharField(max_length=600, unique=True)
    title = models.CharField(max_length=400)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    snippet = models.TextField(blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-fetched_at"]


class FactSuggestion(models.Model):
    """AI taklifi: mavzu, burchak va manbali asosiy fikrlar. Tayyor post matni YOZILMAYDI."""
    STATUS = [("new", "Yangi"), ("used", "Ishlatildi"), ("dismissed", "Rad etildi")]
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="fact_suggestions")
    topic = models.ForeignKey(FactTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions")
    platform = models.CharField(max_length=12, choices=FactTopic.PLATFORMS)
    kind = models.CharField(max_length=6, choices=FactTopic.KIND, default="fact")
    title = models.CharField(max_length=300)
    angle = models.TextField(blank=True)                    # qanday burchakdan yondashish
    why = models.TextField(blank=True)                      # nega aynan shu biznes/maqsad uchun
    format = models.CharField(max_length=40, blank=True)    # karusel / reels / oddiy post ...
    key_points = models.JSONField(default=list, blank=True)  # [{claim, quote, item_id, source, url, tier, verified}]
    verified_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="new", db_index=True)
    by_ai = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
