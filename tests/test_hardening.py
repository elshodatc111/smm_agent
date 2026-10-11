"""Qattiqlashtirish: AI kalit tekshiruvi, model avto-aniqlash, tugma matni, orphan tiklash."""
import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_router import providers as aip
from apps.ai_router.models import AIKey
from apps.ai_router.router import AIRouter, AIUnavailable
from apps.ai_router.types import AIRequest, TaskType
from apps.connections.base import NotFoundError
from apps.jobs.models import Job
from apps.jobs.queue import recover_orphans
from apps.web import ui

pytestmark = pytest.mark.django_db


def test_btn_has_label_and_t():
    b = ui.btn("Salom", "/x/")
    assert b["label"] == "Salom" and b["t"] == "Salom"


def _admin_client():
    u = User.objects.create_user("adm", password="Pass12345!x", is_admin=True)
    c = Client()
    c.force_login(u)
    return c


def test_actions_block_renders_label():
    c = _admin_client()
    r = c.get("/sozlamalar/?tab=kalitlar")
    assert r.status_code == 200
    html = r.content.decode()
    assert ">Cloudflare Worker</button>" in html and ">Mijoz boti</button>" in html


def test_key_format_hints():
    assert aip.key_format_problem("openai", "AIzaXYZ") and "sk-" in aip.key_format_problem("openai", "AIzaXYZ")
    assert aip.key_format_problem("openai", "sk-abc") is None
    assert aip.key_format_problem("claude", "sk-ant-abc") is None
    assert aip.key_format_problem("claude", "sk-abc")


def test_ai_key_add_rejects_bad_key(monkeypatch):
    c = _admin_client()
    r = c.post("/sozlamalar/ai-kalit/qoshish/", {"provider": "openai", "alias": "g1", "key": "xai-123"}, follow=True)
    assert not AIKey.objects.exists()
    assert "sk-" in r.content.decode()
    monkeypatch.setattr(aip, "validate_key", lambda p, k: (False, "rad etildi"))
    c.post("/sozlamalar/ai-kalit/qoshish/", {"provider": "openai", "alias": "g1", "key": "sk-abc"})
    assert not AIKey.objects.exists()
    monkeypatch.setattr(aip, "validate_key", lambda p, k: (True, "ok"))
    c.post("/sozlamalar/ai-kalit/qoshish/", {"provider": "openai", "alias": "g1", "key": "sk-abc"})
    assert AIKey.objects.filter(alias="g1").exists()
    k = AIKey.objects.get(alias="g1")
    k.fail_streak = 3
    k.save()
    c.post(f"/sozlamalar/ai-kalit/{k.pk}/tekshir/")
    k.refresh_from_db()
    assert k.fail_streak == 0


def test_model_autodiscovery_on_404(monkeypatch):
    k = AIKey(provider="openai", alias="g")
    k.set_secret("AIzaTEST")
    k.save()
    calls = []

    class P(aip._Base):
        name = "openai"

        def supports(self, t):
            return True

        def call(self, req, key, model, system):
            calls.append(model)
            if model == "eski-model":
                raise NotFoundError("no longer available")
            return aip.RawAIResponse("Salom dunyo, bu sinov javobi.", 1, 1)

    from apps.core.settings_store import get_setting, set_setting
    set_setting("ai.models", {"openai": "eski-model"})
    monkeypatch.setattr("apps.ai_router.router.discover_model", lambda p, k: "yangi-model")
    r = AIRouter(providers={"openai": P()}, use_fakes=False)
    res = r.run(AIRequest(task=TaskType.CLASSIFY, prompt="salom"))
    assert calls == ["eski-model", "yangi-model"] and res.model == "yangi-model"
    assert get_setting("ai.models")["openai"] == "yangi-model"


def test_ai_unavailable_friendly_message():
    r = AIRouter(providers={}, use_fakes=False)
    with pytest.raises(AIUnavailable) as e:
        r.run(AIRequest(task=TaskType.CLASSIFY, prompt="x"))
    assert "kalit" in e.value.user_message_uz.lower()


def test_recover_orphans():
    j = Job.objects.create(type="x", queue="collect", status="running", locked_by="PC1:111/collect0", locked_at=timezone.now(), run_at=timezone.now())
    other = Job.objects.create(type="x", queue="collect", status="running", locked_by="PC2:5/collect0", locked_at=timezone.now(), run_at=timezone.now())
    assert recover_orphans("PC1:222") == 1
    j.refresh_from_db(); other.refresh_from_db()
    assert j.status == "pending" and other.status == "running"


def test_content_form_has_preview_and_uzbek_labels(settings):
    from django.core.management import call_command

    from apps.businesses.models import Business
    settings.USE_FAKES = True
    call_command("seed_demo")
    u = User.objects.create_user("boss2", password="Boss#2026test!", is_admin=True)
    c = Client()
    c.force_login(u)
    c.post("/biznes-tanlash/", {"business": Business.objects.first().pk})
    assert "Instagram" in c.get("/kalendar/yangi/").content.decode()
    for url in ("/kalendar/yangi/telegram/", "/kalendar/yangi/instagram/", "/kalendar/yangi/youtube/"):
        r = c.get(url)
        assert r.status_code == 200
        html = r.content.decode()
        assert "Oldindan ko'rish" in html and "pv-telegram" in html and "pv-instagram" in html and "pv-youtube" in html
        assert "Post turi" in html and "Sarlavha (ichki nom)" in html and 'id="accMap"' in html
    from apps.content.models import ContentItem
    it = ContentItem.objects.filter(business=Business.objects.first()).first()
    if it:
        assert c.get(f"/kalendar/{it.pk}/tahrir/").status_code in (200, 404)


def test_type_platform_validation_and_options(settings):
    from django.core.management import call_command

    from apps.businesses.models import Business
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem
    settings.USE_FAKES = True
    call_command("seed_demo")
    u = User.objects.create_user("boss3", password="Boss#2026test!", is_admin=True)
    c = Client()
    c.force_login(u)
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    yt = SocialAccount.objects.filter(business=b, platform="youtube").first() or SocialAccount.objects.create(
        business=b, platform="youtube", name="YT", handle="yt1", external_id="x", status="active")
    # YouTube + matn -> xato
    r = c.post("/kalendar/yangi/", {"title": "a", "text": "Salom", "media_type": "text", "targets": [str(yt.pk)]})
    assert r.status_code == 200 and "mumkin emas" in r.content.decode()
    # YouTube + video: opsiyalar saqlanadi
    r = c.post("/kalendar/yangi/", {"title": "a", "text": "Sarlavha\nTavsif", "media_type": "video", "targets": [str(yt.pk)],
                                    "yt_title": "Mening videom", "yt_tags": "smm, uzb", "yt_privacy": "unlisted"})
    assert r.status_code == 302
    it = ContentItem.objects.filter(title="a").latest("pk")
    assert it.options["title"] == "Mening videom" and it.options["tags"] == ["smm", "uzb"] and it.options["privacy"] == "unlisted"


def test_time_suggest_and_ai_endpoints(settings):
    from django.core.management import call_command

    from apps.businesses.models import Business
    settings.USE_FAKES = True
    call_command("seed_demo")
    u = User.objects.create_user("boss4", password="Boss#2026test!", is_admin=True)
    c = Client()
    c.force_login(u)
    c.post("/biznes-tanlash/", {"business": Business.objects.first().pk})
    r = c.get("/kalendar/vaqt/?platform=telegram,instagram").json()
    assert set(r["slots"]) == {"telegram", "instagram"} and r["slots"]["telegram"], r
    s0 = r["slots"]["telegram"][0]
    assert "T" in s0["value"] and "label" in s0 and "reason" in s0
    assert c.get("/kalendar/vaqt/").json().get("error")
    r = c.post("/kalendar/ai/matn/", {"platform": "telegram", "media_type": "image", "topic": "yangi kurs"}).json()
    assert "variants" in r or "error" in r
    r = c.post("/kalendar/ai/ssenariy/", {"platform": "instagram", "media_type": "reel", "topic": "yangi kurs"}).json()
    assert "text" in r or "error" in r


def test_suggest_avoids_busy_slots():
    from datetime import timedelta

    from apps.businesses.models import Business
    from apps.connections.models import SocialAccount
    from apps.content.insights import suggest_times
    from apps.content.models import ContentItem, ContentTarget
    b = Business.objects.create(name="B")
    acc = SocialAccount.objects.create(business=b, platform="telegram", name="T", handle="t", external_id="1", status="active")
    first = suggest_times(b, "telegram")[0]
    from django.utils.dateparse import parse_datetime
    from apps.core.utils import tz
    at = parse_datetime(first["value"]).replace(tzinfo=tz())
    it = ContentItem.objects.create(business=b, title="x", scheduled_at=at, status="scheduled")
    ContentTarget.objects.create(item=it, account=acc)
    again = suggest_times(b, "telegram")
    assert first["value"] not in [s["value"] for s in again]
