from datetime import timedelta

from django.utils import timezone

from apps.ads import services as ads
from apps.ads.models import AdCampaign, AdResult
from apps.jobs import scheduler
from apps.jobs.models import Job
from apps.metrics import analytics, collector
from apps.metrics.models import AccountMetrics, Post, PostMetricsHistory, Story, StoryMetricsHistory, Comment
from apps.tgbot import bot
from apps.tgbot.models import ClientBotUser


def test_collect_fake_account(acc_tg):
    r = collector.collect_account(acc_tg)
    assert r["items"] > 0
    assert AccountMetrics.objects.filter(account=acc_tg).count() == 1
    assert Post.objects.filter(account=acc_tg).count() > 0
    assert PostMetricsHistory.objects.exists() and Comment.objects.exists()
    n = Post.objects.count()
    collector.collect_account(acc_tg)  # dublikat yo'q (platform, external_id)
    assert Post.objects.count() == n
    assert AccountMetrics.objects.filter(account=acc_tg).count() == 2  # tarix qo'shiladi, ustiga yozilmaydi


def test_er_basis():
    from apps.connections.base import PostMetrics
    from datetime import datetime, timezone as tzz
    m = PostMetrics("x", datetime.now(tzz.utc), views=1000, likes=50, comments=10, shares=5, saves=5, reach=500)
    assert collector.compute_er(m, 10000) == (70 / 500, "reach")
    m2 = PostMetrics("x", datetime.now(tzz.utc), views=1000, likes=100)
    assert collector.compute_er(m2, 10000) == (0.1, "views")
    assert collector.compute_er(PostMetrics("x", datetime.now(tzz.utc), likes=10), 100) == (0.1, "followers")


def test_story_history_and_final(acc_ig):
    collector.snapshot_stories(acc_ig)
    collector.snapshot_stories(acc_ig)
    assert StoryMetricsHistory.objects.count() == 2
    Story.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    collector.snapshot_stories(acc_ig)
    assert StoryMetricsHistory.objects.filter(is_final=True).count() == 1 and Story.objects.first().finalized


def test_history_import_marks_done(biz):
    from apps.connections.models import SocialAccount
    a = SocialAccount.objects.create(business=biz, platform="youtube", name="YT", external_id="yt1")
    collector.collect_account(a, mode="history", days=90)
    a.refresh_from_db()
    assert a.history_imported


def test_competitor_collect_via_router(biz, admin):
    from apps.connections.models import Competitor
    from apps.core.settings_store import set_setting
    from apps.providers.impl import FakeProvider
    from apps.providers import router as pr
    pr.register(FakeProvider("tme_public"))
    set_setting("providers.priority", {"telegram": ["tme_public"]}, user=admin)
    c = Competitor.objects.create(business=biz, platform="telegram", handle="rival")
    out = collector.collect_competitor(c, "full")
    assert out["items"] > 1
    from apps.metrics.models import CompetitorMetrics, CompetitorPost
    assert CompetitorMetrics.objects.count() == 1 and CompetitorPost.objects.exists()


def test_scheduler_enqueues_once_per_slot(acc_tg):
    now = timezone.now()
    out1 = scheduler.tick(now)
    out2 = scheduler.tick(now)
    assert out2["collect"] == 0
    assert Job.objects.filter(type="collect_account").count() <= 1


def test_scheduler_history_first(biz):
    from apps.connections.models import SocialAccount
    SocialAccount.objects.create(business=biz, platform="telegram", name="New", history_imported=False)
    scheduler.tick()
    assert Job.objects.filter(type="historical_import").count() == 1
    scheduler.tick()
    assert Job.objects.filter(type="historical_import").count() == 1


def test_scheduler_publishes_due_items(biz, acc_tg, manager):
    from apps.content.models import ContentItem, ContentTarget
    from apps.content.state import transition
    item = ContentItem.objects.create(business=biz, title="t", text="Yangi kurs! Narxi 500000 so'm. Qo'ng'iroq: +998 90 123 45 67", scheduled_at=timezone.now(), created_by=manager)
    ContentTarget.objects.create(item=item, account=acc_tg)
    transition(item, "scheduled", manager)
    scheduler.tick()
    assert Job.objects.filter(type="publish_item", queue="publish").count() == 1


def test_anomaly_detection(acc_tg):
    now = timezone.now()
    for i in range(14):
        AccountMetrics.objects.create(business=acc_tg.business, account=acc_tg, taken_at=now - timedelta(days=14 - i), followers=1000 + i * 3 + (i % 2))
    AccountMetrics.objects.create(business=acc_tg.business, account=acc_tg, taken_at=now, followers=1500)
    a = analytics.detect_anomalies(acc_tg)
    assert a and a["direction"] == "o'sish"


# ---------- reklama ----------
def test_forecast_transparent_and_ordered(biz):
    f = ads.forecast(biz, 5_000_000, "telegram_ads")
    s = f["scenarios"]
    assert s["past"]["sales"] <= s["ortacha"]["sales"] <= s["yuqori"]["sales"]
    assert f["assumptions"]["cpm"]["source"] == "industry_template" and f["disclaimer"]
    assert s["ortacha"]["revenue"] > 0


def test_forecast_calibrates_from_results(biz):
    c = AdCampaign.objects.create(business=biz, name="k", platform="telegram_ads", budget=1000000)
    for i in range(4):
        AdResult.objects.create(campaign=c, date=timezone.now().date() - timedelta(days=i), spend=250000, impressions=10000, clicks=400, leads=40, sales=8, revenue=4000000)
    f = ads.forecast(biz, 1_000_000, "telegram_ads")
    assert f["assumptions"]["ctr"]["source"] == "calibrated" and f["assumptions"]["ctr"]["sample"] == 4


def test_ad_candidates_need_min_age(biz, acc_tg):
    collector.collect_account(acc_tg)
    recs = ads.find_candidates(biz)
    assert recs and all(r.post.published_at < timezone.now() - timedelta(hours=24) for r in recs)


# ---------- bot ----------
def test_bot_invite_flow_and_isolation(biz, biz2, admin):
    code = bot.create_invite([biz.pk], admin, "Mijoz")
    api = bot.FakeBotAPI()
    bot.handle_update({"message": {"from": {"id": 7, "first_name": "Ali"}, "chat": {"id": 7}, "text": f"/start {code}"}}, api)
    assert ClientBotUser.objects.get(tg_user_id=7).business_ids == [biz.pk]
    # kod bir martalik
    api2 = bot.FakeBotAPI()
    bot.handle_update({"message": {"from": {"id": 8, "first_name": "B"}, "chat": {"id": 8}, "text": f"/start {code}"}}, api2)
    assert not ClientBotUser.objects.filter(tg_user_id=8).exists() and "yaroqsiz" in api2.sent[0][1]
    # begona foydalanuvchi ma'lumot ola olmaydi
    api3 = bot.FakeBotAPI()
    bot.handle_update({"callback_query": {"id": "1", "from": {"id": 99}, "message": {"chat": {"id": 99}}, "data": "kpi"}}, api3)
    assert "taklif kodi" in api3.sent[0][1].lower()


def test_bot_expired_invite(biz, admin):
    from apps.tgbot.models import ClientInvite
    code = bot.create_invite([biz.pk], admin)
    ClientInvite.objects.update(expires_at=timezone.now() - timedelta(hours=1))
    assert bot.redeem(code, 5, "x") is None


def test_bot_section_permission(biz, admin):
    u = ClientBotUser.objects.create(tg_user_id=5, business_ids=[biz.pk], current_business=biz.pk, sections={str(biz.pk): ["kpi"]})
    api = bot.FakeBotAPI()
    bot.handle_update({"callback_query": {"id": "1", "from": {"id": 5}, "message": {"chat": {"id": 5}}, "data": "top"}}, api)
    assert "ruxsat berilmagan" in api.sent[0][1]
    api = bot.FakeBotAPI()
    bot.handle_update({"callback_query": {"id": "1", "from": {"id": 5}, "message": {"chat": {"id": 5}}, "data": "kpi"}}, api)
    assert "Obunachilar" in api.sent[0][1]


def test_bot_has_no_approval_flow(biz, manager, admin):
    ClientBotUser.objects.create(tg_user_id=5, business_ids=[biz.pk], current_business=biz.pk)
    api = bot.FakeBotAPI()
    ev = lambda d: {"callback_query": {"id": "1", "from": {"id": 5}, "message": {"chat": {"id": 5}}, "data": d}}
    bot.handle_update(ev("appr"), api)   # eski tugma: endi tasdiqlash yo'q
    assert not any("Tasdiqlayman" in str(m) for m in api.sent)
    assert "approve_posts" not in [r[0] for r in __import__("apps.tgbot.models", fromlist=["SECTIONS"]).SECTIONS]
