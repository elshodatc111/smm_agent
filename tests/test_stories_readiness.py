"""Stories: akkaunt holati, oldindan tekshiruv, vaqt tavsiyasi, orqa fonda tayyorlash, jonli holat, bildirishnoma."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import Notification
from apps.jobs.models import Job
from apps.stories import services, tgclient
from apps.stories.models import Story, StoryAccount, StoryTarget
from tests.test_stories import cl, create, mk_accs, run_all  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    tgclient.FAKE_FAIL.clear()
    tgclient.FAKE_REMAINS.clear()


def test_state_codes():
    a, b, c, d = mk_accs(4)
    b.cooldown_until = timezone.now() + timedelta(hours=1)
    b.save()
    c.status = "error"
    c.save()
    d.can_post, d.checked_at = False, timezone.now()
    d.save()
    codes = {s["id"]: s["code"] for s in services.states([a, b, c, d])}
    assert codes == {a.pk: "ready", b.pk: "cooldown", c.pk: "auth", d.pk: "limit"}
    # rejalashtirilgan vaqt sovish tugagandan keyin bo'lsa, muammo emas
    assert services.account_state(b, timezone.now() + timedelta(hours=2))["code"] == "ready"


def test_check_account_updates(cl):
    a = mk_accs(1)[0]
    tgclient.FAKE_REMAINS[a.pk] = 3
    st = services.check_account(a)
    a.refresh_from_db()
    assert a.can_post is True and a.remains == 3 and "3" in st["label"]
    tgclient.FAKE_FAIL[a.pk] = "limit"
    assert services.check_account(a)["code"] == "limit"
    tgclient.FAKE_FAIL[a.pk] = "auth"
    services.check_account(a)
    a.refresh_from_db()
    assert a.status == "error"
    assert Notification.objects.filter(type="stories.account").exists()


def test_check_endpoint(cl):
    a = mk_accs(1)[0]
    r = cl.post("/stories/tekshir/", {"pk": a.pk}).json()
    assert r["ok"] and r["state"]["code"] == "ready"
    assert cl.post("/stories/tekshir/").json()["queued"] is True
    assert Job.objects.filter(type="story_check_accounts").exists()


def test_preflight_endpoint_and_suggestions(cl):
    a, b = mk_accs(2)
    b.cooldown_until = timezone.now() + timedelta(hours=2)
    b.save()
    d = cl.get(f"/stories/tayyorlik/?accounts={a.pk}&accounts={b.pk}").json()
    assert d["problems"] == 1 and d["ready"] == 1 and d["finish"] and d["suggestions"]
    assert d["suggestions"][0]["label"].startswith("Eng erta")
    # boshqa story shu vaqtga rejalashtirilgan bo'lsa — to'qnashuv
    create(cl, [a.pk])
    d = cl.get(f"/stories/tayyorlik/?accounts={a.pk}").json()
    assert d["conflicts"]


def test_preflight_skip_removes_problem_accounts(cl):
    a, b = mk_accs(2)
    b.cooldown_until = timezone.now() + timedelta(hours=2)
    b.save()
    create(cl, [a.pk, b.pk], preflight="skip")
    s = Story.objects.get()
    assert [t.account_id for t in s.targets.all()] == [a.pk]
    Story.objects.all().delete()
    create(cl, [a.pk, b.pk], preflight="all")
    assert Story.objects.get().targets.count() == 2


def test_limit_error_marks_account(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk])
    tgclient.FAKE_FAIL[a.pk] = "limit"
    run_all()
    a.refresh_from_db()
    assert a.can_post is False
    assert services.account_state(a)["code"] == "limit"


def test_status_endpoint_and_worker_flag(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk])
    d = cl.get("/stories/holat/").json()
    assert d["worker"]["alive"] is False and d["stories"][0]["total"] == 1 and d["accounts"][0]["code"] == "ready"
    from apps.jobs.models import WorkerHeartbeat
    WorkerHeartbeat.objects.create(name="w1", beat_at=timezone.now())
    assert cl.get("/stories/holat/").json()["worker"]["alive"] is True


def test_result_notification_on_done(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk])
    run_all()
    assert Story.objects.get().status == "done"
    assert Notification.objects.filter(type="stories.result", title__startswith="Story hammasiga").exists()


def test_prepare_failure_and_watchdog(cl, monkeypatch):
    from apps.stories import music
    a = mk_accs(1)[0]
    create(cl, [a.pk], music_id="9000", music_len="10")
    monkeypatch.setattr(music, "build_video", lambda *a, **k: (_ for _ in ()).throw(music.MusicError("sinov xatosi")))
    for j in Job.objects.filter(type="story_prepare"):
        services.prepare_story(j.payload["story_id"], j.payload["accounts"], j.payload.get("when"))
    s = Story.objects.get()
    assert s.status == "failed" and "sinov" in s.prepare_error and s.targets.count() == 0
    assert Notification.objects.filter(type="stories.result", title__startswith="Story tayyorlanmadi").exists()
    # qotib qolgan
    s.status = "preparing"
    s.save()
    Story.objects.filter(pk=s.pk).update(created_at=timezone.now() - timedelta(minutes=40))
    Job.objects.filter(type="story_prepare").delete()
    assert services.watchdog() == 1 and Story.objects.get().status == "failed"


def test_cancel_preparing(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk], music_id="9000", music_len="10")
    s = Story.objects.get()
    cl.post(f"/stories/{s.pk}/amal/", {"action": "cancel"})
    for j in Job.objects.filter(type="story_prepare"):
        services.prepare_story(j.payload["story_id"], j.payload["accounts"], j.payload.get("when"))
    s.refresh_from_db()
    assert s.status == "cancelled" and s.targets.count() == 0


def test_scheduler_enqueues_check(cl):
    from apps.jobs.scheduler import tick
    mk_accs(1)
    tick()
    assert Job.objects.filter(type="story_check_accounts").exists()


def test_pages_render(cl):
    mk_accs(2)
    for u in ("/stories/", "/stories/yangi/", "/stories/akkauntlar/"):
        r = cl.get(u)
        assert r.status_code == 200
    assert "stCheckAll" in cl.get("/stories/yangi/").content.decode()
    assert "Hozir jarayonda" in cl.get("/stories/").content.decode()
