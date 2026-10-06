from datetime import timedelta

import pytest
from django.utils import timezone

from apps.connections import fake
from apps.connections.base import TransientError
from apps.content import services, temphost
from apps.content.models import ContentItem, ContentTarget, PublishAttempt
from apps.content.rules import run_rules, similarity
from apps.content.state import transition
from apps.core.settings_store import set_setting

GOOD = "Yangi kurs boshlandi! Narxi 500000 so'm, chegirma 20%. Aloqa: +998 90 123 45 67. Ro'yxatdan o'ting."


def mk_item(biz, acc, user, text=GOOD, **kw):
    item = ContentItem.objects.create(business=biz, title="Test post", text=text, created_by=user,
                                      scheduled_at=kw.pop("scheduled_at", timezone.now() + timedelta(minutes=5)), **kw)
    ContentTarget.objects.create(item=item, account=acc)
    return item


def approve(item, mgr):
    """Tasdiqlash bosqichi yo'q — endi to'g'ridan-to'g'ri rejalashtirish."""
    return None


def test_full_happy_path(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager)
    approve(item, manager)
    transition(item, "scheduled", manager)
    item.scheduled_at = timezone.now()
    item.save()
    t = item.targets.first()
    res = services.publish_target(item.pk, t.pk)
    item.refresh_from_db()
    assert item.status == "published" and res["published"]
    assert fake.PUBLISH_CALLS == [services._idem_key(item, t)]


def test_idempotent_second_run_no_double_post(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    t = item.targets.first()
    services.publish_target(item.pk, t.pk)
    services.publish_target(item.pk, t.pk)
    assert len(fake.PUBLISH_CALLS) == 1 and len(fake.PUBLISHED) == 1


def test_draft_never_publishes(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    t = item.targets.first()
    res = services.publish_target(item.pk, t.pk)
    assert "blocked" in res and fake.PUBLISH_CALLS == []


def test_kill_switch_blocks(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    biz.autopublish_enabled = False
    biz.save()
    t = item.targets.first()
    assert services.publish_target(item.pk, t.pk) == {"blocked": "kill_switch"}
    assert fake.PUBLISH_CALLS == []


def test_account_kill_switch(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    acc_tg.autopublish_enabled = False
    acc_tg.save()
    assert services.publish_target(item.pk, item.targets.first().pk) == {"blocked": "kill_switch"}


def test_missed_window(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    ContentItem.objects.filter(pk=item.pk).update(scheduled_at=timezone.now() - timedelta(hours=2))
    res = services.publish_target(item.pk, item.targets.first().pk)
    item.refresh_from_db()
    assert res == {"failed": "missed_window"} and item.status == "failed" and not fake.PUBLISH_CALLS





def test_retry_then_success(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    t = item.targets.first()
    fake.FAIL_NEXT_PUBLISH.append(TransientError("net"))
    with pytest.raises(TransientError):
        services.publish_target(item.pk, t.pk)
    assert PublishAttempt.objects.get(target=t).status == "failed"
    services.publish_target(item.pk, t.pk)
    t.refresh_from_db()
    assert t.status == "published" and len(fake.PUBLISHED) == 1


def test_non_retryable_fails_and_manual_retry(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, scheduled_at=timezone.now())
    approve(item, manager)
    transition(item, "scheduled", manager)
    t = item.targets.first()
    from apps.connections.base import ContentRejectedError
    fake.FAIL_NEXT_PUBLISH.append(ContentRejectedError("format"))
    services.publish_target(item.pk, t.pk)
    item.refresh_from_db()
    assert item.status == "failed"
    n = services.retry_failed(item, manager)
    assert n == 1
    item.refresh_from_db()
    assert item.status == "scheduled"


# ---------- qoidalar ----------
def test_rules_block_wrong_phone_and_price(biz, acc_tg, manager):
    item = mk_item(biz, acc_tg, manager, text="Kurs narxi 900000 so'm. Tel: +998 91 999 88 77")
    r = run_rules(item, "telegram")
    ids = {p.rule_id for p in r.problems}
    assert r.status == "block" and "truth.facts_match" in ids


def test_rules_pass_good_text(biz, acc_tg, manager):
    assert run_rules(mk_item(biz, acc_tg, manager), "telegram").status in ("pass", "warn")


def test_rules_banned_words_and_length(biz, acc_tg, manager):
    from apps.businesses.services import approve_brand, save_brand_version
    approve_brand(save_brand_version(biz, "x", structured={"banned_words": ["arzon"]}, user=manager), manager)
    r = run_rules(mk_item(biz, acc_tg, manager, text="Juda arzon! " + "a" * 5000), "telegram")
    ids = {p.rule_id for p in r.problems}
    assert {"brand.banned_words", "platform.text_length"} <= ids and r.status == "block"


def test_similarity_blocks_copy(biz, acc_tg, manager):
    from apps.connections.models import Competitor
    from apps.metrics.models import CompetitorPost
    c = Competitor.objects.create(business=biz, platform="telegram", handle="c")
    CompetitorPost.objects.create(competitor=c, business_id=biz.pk, external_id="1", text=GOOD)
    r = run_rules(mk_item(biz, acc_tg, manager, text=GOOD), "telegram")
    assert any(p.rule_id == "orig.competitor_similarity" and p.severity == "block" for p in r.problems)
    assert similarity("a b c d e f", "x y z") == 0





# ---------- vaqtinchalik hosting ----------
def test_r2_cap_enforced(tmp_path, settings, admin, monkeypatch):
    set_setting("publish.r2.max_gb", 0.00001, user=admin)  # ~10 KB
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x" * 8000)
    monkeypatch.setattr(temphost, "hosts", lambda fake_: [temphost.R2Host()])
    monkeypatch.setattr(temphost.R2Host, "available", lambda self, size: True)
    monkeypatch.setattr(temphost.R2Host, "upload", lambda self, p, k, t: "https://r2/x")
    temphost.host_file(str(f))
    with pytest.raises(temphost.WaitingForSpace):
        temphost.host_file(str(f))
    assert temphost.r2_used_bytes() <= 10737


def test_temp_objects_cleaned_after_publish(biz, acc_tg, manager, tmp_path):
    item = mk_item(biz, acc_tg, manager)
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    o = temphost.host_file(str(f), item, fake=True)
    assert temphost.FakeHost.store
    services.cleanup_temp_for(item)
    o.refresh_from_db()
    assert o.status == "deleted" and not temphost.FakeHost.store
