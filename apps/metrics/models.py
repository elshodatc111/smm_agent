from django.conf import settings
from django.db import models


class AccountMetrics(models.Model):
    """Hisob ko'rsatkichlari tarixi (INSERT-only)."""
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="+")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="metrics")
    taken_at = models.DateTimeField(db_index=True)
    followers = models.BigIntegerField(null=True, blank=True)
    following = models.BigIntegerField(null=True, blank=True)
    posts_count = models.IntegerField(null=True, blank=True)
    reach = models.BigIntegerField(null=True, blank=True)
    impressions = models.BigIntegerField(null=True, blank=True)
    views = models.BigIntegerField(null=True, blank=True)
    profile_visits = models.BigIntegerField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["account", "taken_at"]), models.Index(fields=["business", "taken_at"])]


class Post(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="posts")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="posts")
    platform = models.CharField(max_length=12)
    external_id = models.CharField(max_length=160)
    media_type = models.CharField(max_length=12, default="text")
    text = models.TextField(blank=True)
    url = models.CharField(max_length=400, blank=True)
    published_at = models.DateTimeField(db_index=True)
    duration_sec = models.FloatField(null=True, blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    media_urls = models.JSONField(default=list, blank=True)
    content_item = models.ForeignKey("content.ContentItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="posts")
    first_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("platform", "external_id")]
        indexes = [models.Index(fields=["business", "published_at"]), models.Index(fields=["account", "published_at"])]
        ordering = ["-published_at"]


class PostMetricsHistory(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="history")
    business_id = models.PositiveBigIntegerField(db_index=True)
    taken_at = models.DateTimeField(db_index=True)
    age_hours = models.FloatField(default=0)
    views = models.BigIntegerField(null=True, blank=True)
    likes = models.BigIntegerField(null=True, blank=True)
    comments = models.BigIntegerField(null=True, blank=True)
    shares = models.BigIntegerField(null=True, blank=True)
    saves = models.BigIntegerField(null=True, blank=True)
    reach = models.BigIntegerField(null=True, blank=True)
    reactions = models.JSONField(default=dict, blank=True)
    watch_time_sec = models.FloatField(null=True, blank=True)
    avg_view_duration_sec = models.FloatField(null=True, blank=True)
    ctr = models.FloatField(null=True, blank=True)
    er = models.FloatField(null=True, blank=True)
    er_basis = models.CharField(max_length=10, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["post", "taken_at"])]


class Story(models.Model):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="+")
    account = models.ForeignKey("connections.SocialAccount", on_delete=models.CASCADE, related_name="stories")
    external_id = models.CharField(max_length=160)
    published_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    media_type = models.CharField(max_length=12, default="story")
    url = models.CharField(max_length=400, blank=True)
    finalized = models.BooleanField(default=False)

    class Meta:
        unique_together = [("account", "external_id")]


class StoryMetricsHistory(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="history")
    taken_at = models.DateTimeField()
    views = models.BigIntegerField(null=True, blank=True)
    reach = models.BigIntegerField(null=True, blank=True)
    replies = models.BigIntegerField(null=True, blank=True)
    shares = models.BigIntegerField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    is_final = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["story", "taken_at"])]


class CompetitorMetrics(models.Model):
    competitor = models.ForeignKey("connections.Competitor", on_delete=models.CASCADE, related_name="metrics")
    business_id = models.PositiveBigIntegerField(db_index=True)
    taken_at = models.DateTimeField(db_index=True)
    followers = models.BigIntegerField(null=True, blank=True)
    posts_count = models.IntegerField(null=True, blank=True)
    views = models.BigIntegerField(null=True, blank=True)
    provider = models.CharField(max_length=40, blank=True)


class CompetitorPost(models.Model):
    competitor = models.ForeignKey("connections.Competitor", on_delete=models.CASCADE, related_name="posts")
    business_id = models.PositiveBigIntegerField(db_index=True)
    external_id = models.CharField(max_length=160)
    media_type = models.CharField(max_length=12, blank=True)
    text = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    views = models.BigIntegerField(null=True, blank=True)
    likes = models.BigIntegerField(null=True, blank=True)
    comments = models.BigIntegerField(null=True, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    alerted = models.BooleanField(default=False)   # «raqobatchi posti yaxshi chiqdi» ogohlantirishi yuborilgan

    class Meta:
        unique_together = [("competitor", "external_id")]


class CompetitorPostMetric(models.Model):
    post = models.ForeignKey(CompetitorPost, on_delete=models.CASCADE, related_name="history")
    taken_at = models.DateTimeField()
    views = models.BigIntegerField(null=True, blank=True)
    likes = models.BigIntegerField(null=True, blank=True)
    comments = models.BigIntegerField(null=True, blank=True)


class CollectionRun(models.Model):
    """Har bir yig'ish natijasi, sarfi va xatosi (FR-C6)."""
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    business_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    account = models.ForeignKey("connections.SocialAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    competitor = models.ForeignKey("connections.Competitor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=30)
    ok = models.BooleanField(default=True)
    items = models.PositiveIntegerField(default=0)
    cost = models.FloatField(default=0)
    cost_unit = models.CharField(max_length=20, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    error = models.CharField(max_length=400, blank=True)
    duration_ms = models.FloatField(null=True, blank=True)


class DailyStat(models.Model):
    """Har kunlik yig'ma: bir biznes/akkaunt uchun kun bo'yicha bitta qator (kechasi saqlanadi, o'zgarmas tarix)."""
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="+")
    account = models.ForeignKey("connections.SocialAccount", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    platform = models.CharField(max_length=12, blank=True)
    day = models.DateField(db_index=True)
    followers = models.BigIntegerField(null=True, blank=True)
    followers_delta = models.IntegerField(default=0)
    posts = models.IntegerField(default=0)
    stories = models.IntegerField(default=0)
    views = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    saves = models.BigIntegerField(default=0)
    story_views = models.BigIntegerField(default=0)

    class Meta:
        unique_together = [("business", "account", "day")]
        indexes = [models.Index(fields=["business", "day"])]
