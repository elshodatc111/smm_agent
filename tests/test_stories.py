"""Telegram Stories: akkauntlar, yuklash, oraliq, Premium xatosi, rejalashtirish, kalendar, statistika, ruxsatlar, mustaqillik."""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.core import crypto
from apps.jobs.models import Job
from apps.stories import services, tgclient
from apps.stories.models import Story, StoryAccount, StoryStat, StoryTarget

pytestmark = pytest.mark.django_db


def png(name="a.png"):
    from io import BytesIO

    from PIL import Image
    b = BytesIO()
    Image.new("RGB", (60, 100), (200, 30, 30)).save(b, "PNG")
    return SimpleUploadedFile(name, b.getvalue(), content_type="image/png")


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    tgclient.FAKE_FAIL.clear()


@pytest.fixture
def cl(admin):
    c = Client()
    c.force_login(admin)
    return c


def mk_accs(n=3, premium=()):
    out = []
    for i in range(n):
        out.append(StoryAccount.objects.create(name=f"A{i}", phone=f"+99890000000{i}", session_enc=crypto.encrypt("fake"), is_premium=i in premium))
    return out


def create(cl, ids, **kw):
    data = {"media": png(), "accounts": [str(i) for i in ids], "when": "now", "caption": "Salom", **kw}
    return cl.post("/stories/yangi/", data)


def run_all():
    """Navbatdagi story_publish vazifalarini ketma-ket bajaradi."""
    for j in Job.objects.filter(type="story_publish", status="pending").order_by("run_at"):
        services.publish_target(j.payload["target_id"])


def test_account_limit_30(cl):
    for i in range(30):
        StoryAccount.objects.create(name=f"x{i}", phone=f"+9989{i:08d}", session_enc="x")
    r = cl.post("/stories/akkauntlar/qosh/", {"name": "Y", "phone": "+998911111111"}, follow=True)
    assert StoryAccount.objects.count() == 30 and "30" in r.content.decode()


def test_add_account_fake_flow(cl):
    cl.post("/stories/akkauntlar/qosh/", {"name": "Birinchi", "phone": "+998901112233"})
    a = StoryAccount.objects.get()
    assert a.name == "Birinchi" and a.string_session() == "fake"


def test_create_all_accounts_staggered(cl):
    accs = mk_accs(4)
    r = create(cl, [], all="1")
    assert r.status_code == 302
    s = Story.objects.get()
    ts = list(s.targets.order_by("run_at"))
    assert len(ts) == 4 and s.kind == "photo"
    gaps = [(b.run_at - a.run_at).total_seconds() for a, b in zip(ts, ts[1:])]
    assert all(60 <= g <= 180 for g in gaps)
    assert Job.objects.filter(type="story_publish").count() == 4
    run_all()
    assert set(s.targets.values_list("status", flat=True)) == {"sent"}
    s.refresh_from_db()
    assert s.status == "done" and all(t.tg_story_id for t in s.targets.all())
    assert accs


def test_selected_accounts_only(cl):
    a, b, c = mk_accs(3)
    create(cl, [a.pk, c.pk])
    assert set(Story.objects.get().targets.values_list("account_id", flat=True)) == {a.pk, c.pk}


def test_non_premium_errors_listed(cl):
    a, b = mk_accs(2, premium=(1,))
    tgclient.FAKE_FAIL[a.pk] = "premium"
    create(cl, [a.pk, b.pk])
    run_all()
    s = Story.objects.get()
    s.refresh_from_db()
    t = s.targets.get(account=a)
    assert t.status == "error" and t.error_code == "premium" and s.status == "partial"
    html = cl.get(f"/stories/{s.pk}/").content.decode()
    assert "Premium talab qilingan" in html and a.name in html


def test_long_caption_blocks_non_premium_only(cl):
    a, b = mk_accs(2, premium=(1,))
    create(cl, [a.pk, b.pk], caption="x" * 300)
    run_all()
    s = Story.objects.get()
    assert s.targets.get(account=a).error_code == "premium"
    assert s.targets.get(account=b).status == "sent"


def test_flood_reschedules_and_cooldown(cl):
    a, = mk_accs(1)
    tgclient.FAKE_FAIL[a.pk] = "flood"
    create(cl, [a.pk])
    run_all()
    t = StoryTarget.objects.get()
    a.refresh_from_db()
    assert t.status == "pending" and a.cooldown_until and t.run_at > timezone.now()
    assert Job.objects.filter(type="story_publish").count() == 2


def test_auth_error_marks_account(cl):
    a, = mk_accs(1)
    tgclient.FAKE_FAIL[a.pk] = "auth"
    create(cl, [a.pk])
    run_all()
    a.refresh_from_db()
    assert a.status == "error" and StoryTarget.objects.get().error_code == "auth"


def test_retry_after_error(cl):
    a, = mk_accs(1)
    tgclient.FAKE_FAIL[a.pk] = "media"
    create(cl, [a.pk])
    run_all()
    t = StoryTarget.objects.get()
    assert t.status == "error"
    tgclient.FAKE_FAIL.clear()
    cl.post(f"/stories/{t.story_id}/amal/", {"action": "retry", "target": t.pk})
    services.publish_target(t.pk)
    t.refresh_from_db()
    assert t.status == "sent"


def test_schedule_future_and_calendar(cl):
    a, = mk_accs(1)
    when = (timezone.localtime(timezone.now()) + timedelta(days=2)).replace(hour=15, minute=30)
    create(cl, [a.pk], when="later", scheduled_at=when.strftime("%Y-%m-%dT%H:%M"), title="Kalendar sinovi")
    s = Story.objects.get()
    assert s.status == "scheduled" and s.scheduled_at > timezone.now()
    html = cl.get(f"/stories/kalendar/?m={when.year}-{when.month}").content.decode()
    assert "Kalendar sinovi" in html


def test_past_schedule_rejected(cl):
    a, = mk_accs(1)
    r = create(cl, [a.pk], when="later", scheduled_at="2020-01-01T10:00")
    assert r.status_code == 200 and not Story.objects.exists()


def test_stats_history(cl):
    a, = mk_accs(1)
    create(cl, [a.pk])
    run_all()
    t = StoryTarget.objects.get()
    assert Job.objects.filter(type="story_stats").count() == 4
    assert services.refresh_stats(t.pk) and services.refresh_stats(t.pk)
    t.refresh_from_db()
    assert t.views > 0 and StoryStat.objects.filter(target=t).count() == 2
    assert "Ko'rishlar tarixi" in cl.get(f"/stories/{t.story_id}/").content.decode()
    assert str(t.views) in cl.get("/stories/statistika/").content.decode()


def test_cancel_pending_keeps_sent(cl):
    a, b = mk_accs(2)
    create(cl, [a.pk, b.pk])
    first = StoryTarget.objects.order_by("run_at").first()
    services.publish_target(first.pk)
    s = Story.objects.get()
    cl.post(f"/stories/{s.pk}/amal/", {"action": "cancel"})
    assert set(s.targets.values_list("status", flat=True)) == {"sent", "skipped"}


def test_validation_errors(cl):
    a, = mk_accs(1)
    assert create(cl, [a.pk], link_url="ftp://x").status_code == 200
    assert create(cl, [a.pk], geo_lat="200", geo_lon="10").status_code == 200
    assert cl.post("/stories/yangi/", {"accounts": [str(a.pk)], "when": "now"}).status_code == 200      # fayl yo'q
    assert create(cl, []).status_code == 200                                                              # akkaunt yo'q
    assert not Story.objects.exists()


def test_all_features_saved(cl):
    a, = mk_accs(1)
    create(cl, [a.pk], period="43200", privacy="close", pinned="1", noforwards="1", link_url="https://t.me/x", reaction="🔥", geo_lat="41.3", geo_lon="69.2")
    s = Story.objects.get()
    assert (s.period, s.privacy, s.pinned, s.noforwards, s.link_url, s.reaction, s.geo_lat) == (43200, "close", True, True, "https://t.me/x", "🔥", 41.3)


def test_pages_render_and_media_served(cl):
    a, = mk_accs(1)
    create(cl, [a.pk])
    s = Story.objects.get()
    for u in ("/stories/", "/stories/akkauntlar/", "/stories/yangi/", "/stories/kalendar/", "/stories/statistika/", f"/stories/{s.pk}/"):
        assert cl.get(u).status_code == 200, u
    assert cl.get(f"/stories/{s.pk}/media/").status_code == 200


def test_permissions_and_nav(db):
    u = User.objects.create_user("oddiy", password="x12345678")
    c = Client()
    c.force_login(u)
    assert c.get("/stories/").status_code == 403
    adm = User.objects.create_user("adm2", password="x12345678", is_admin=True)
    c.force_login(adm)
    assert "Telegram Stories" in c.get("/stories/").content.decode()


def test_independent_from_content_tables(cl):
    """Story yaratish kontent/biznes jadvallariga tegmaydi."""
    from apps.content.models import ContentItem
    from apps.jobs.models import Job as J
    a, = mk_accs(1)
    create(cl, [a.pk])
    assert not ContentItem.objects.exists()
    assert set(J.objects.values_list("type", flat=True)) == {"story_publish"}
