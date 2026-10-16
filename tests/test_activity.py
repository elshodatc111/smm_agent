import pytest
from datetime import date
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def _c(settings, name="actboss"):
    settings.USE_FAKES = True
    __import__("tests.demo_seed", fromlist=["seed"]).seed()
    u = User.objects.create_user(name, password="Boss#2026test!", is_admin=True)
    c = Client(); c.force_login(u)
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    return c, u, b


def test_activity_page_history_and_digest(settings):
    c, u, b = _c(settings)
    r = c.post("/kalendar/yangi/", {"title": "Tarix test", "text": "Salom", "media_type": "text", "scheduled_at": ""})
    from apps.content.models import ContentItem
    it = ContentItem.objects.filter(title="Tarix test").first()
    assert it and AuditLog.objects.filter(action="content.create", user=u).exists()
    html = c.get("/faoliyat/").content.decode()
    assert "Yangi kontent yaratdi" in html and "actboss" in html
    assert "Yangi kontent yaratdi" not in c.get("/faoliyat/?action=cloud").content.decode()
    d = c.get(f"/kalendar/{it.pk}/").content.decode()
    assert "Tarix — kim nima qildi" in d and "Yangi kontent yaratdi" in d
    from apps.web.views_activity import build_digest
    from apps.core.utils import local
    from django.utils import timezone
    txt = build_digest(local(timezone.now()).date())
    assert "actboss" in txt and "Yangi kontent yaratdi" in txt
    from apps.content.jobs import activity_digest
    from apps.jobs.queue import JobContext
    assert activity_digest.__name__


def test_activity_forbidden_for_plain_viewer(settings):
    c, u, b = _c(settings, "adm2")
    v = User.objects.create_user("viewer1", password="Pass12345!x")
    cv = Client(); cv.force_login(v)
    assert cv.get("/faoliyat/").status_code in (302, 403, 404)


def test_bottom_nav_and_crop_fields(settings):
    c, u, b = _c(settings, "adm3")
    h = c.get("/kalendar/yangi/telegram/").content.decode()
    assert 'class="bnav"' in h and 'id="id_crop_zoom"' in h and "cloudPickBtn" in h and 'id="cropBox"' in h
    r = c.get("/cloudflare/tanlash/?kind=image").json()
    assert "files" in r or "error" in r


def test_attach_cloud_file_and_crop_saved(settings, monkeypatch, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c, u, b = _c(settings, "adm4")
    from apps.content.models import ContentItem, TempObject
    from apps.content import temphost
    from PIL import Image
    import io
    buf = io.BytesIO(); Image.new("RGB", (200, 300), "red").save(buf, "JPEG")
    o = TempObject.objects.create(key="k1", backend="fake", filename="foto.jpg", status="uploaded", business=b, size=len(buf.getvalue()))
    monkeypatch.setattr(temphost, "view_url", lambda obj: "http://x/y.jpg")
    class R:
        content = buf.getvalue()
        def raise_for_status(self): pass
    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    from apps.connections.models import SocialAccount
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    r = c.post("/kalendar/yangi/", {"title": "Bulut", "text": "x", "media_type": "image", "targets": [str(acc.pk)], "cloud_ids": [str(o.pk)],
                                    "media_size": "ig_4x5", "fit_mode": "crop", "crop_x": "0.3", "crop_y": "0.6", "crop_zoom": "1.5"})
    assert r.status_code == 302, r.content[:300]
    it = ContentItem.objects.get(title="Bulut")
    assert it.assets.count() == 1 and it.assets.first().cloud_id == o.pk
    assert it.options["crop"] == {"x": 0.3, "y": 0.6, "z": 1.5}


def test_asset_manage_ready_studio_and_media_card(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c, u, b = _c(settings, "adm5")
    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image
    import io
    from apps.content.models import ContentItem, TempObject
    from apps.connections.models import SocialAccount
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    def img(n):
        buf = io.BytesIO(); Image.new("RGB", (400, 500), "blue").save(buf, "JPEG"); return SimpleUploadedFile(n, buf.getvalue(), "image/jpeg")
    r = c.post("/kalendar/yangi/", {"title": "Karusel", "text": "x", "media_type": "carousel", "targets": [str(acc.pk)], "files": [img("a.jpg"), img("b.jpg")]})
    assert r.status_code == 302
    it = ContentItem.objects.get(title="Karusel")
    assert it.assets.count() == 2
    # bir nechta qo'shish
    c.post(f"/kalendar/{it.pk}/fayl/", {"files": [img("c.jpg"), img("d.jpg")]})
    assert it.assets.count() == 4
    a = it.assets.first()
    c.post(f"/kalendar/{it.pk}/fayl/{a.pk}/ochir/")
    assert it.assets.count() == 3
    a2 = it.assets.first()
    c.post(f"/kalendar/{it.pk}/fayl/{a2.pk}/almashtir/", {"file": img("new.jpg")})
    a2.refresh_from_db(); assert a2.size > 0
    html = c.get(f"/kalendar/{it.pk}/").content.decode()
    assert "addPick" in html
    # karusel soni qoidasi
    from apps.content.rules import run_rules
    for x in it.assets.all()[1:]:
        x.delete()
    assert any(p.rule_id == "platform.media_count" for p in run_rules(it, "instagram").problems)
    # kutubxona
    t = TempObject.objects.create(key="k9", backend="fake", filename="logo.png", status="uploaded", business=b, size=10)
    assert c.post(f"/cloudflare/{t.pk}/teg/", {"tags": "Aksiya, KURS"}).status_code == 302
    t.refresh_from_db(); assert t.tags == "aksiya,kurs"
    assert c.get("/cloudflare/?tag=aksiya").status_code == 200
    j = c.get("/cloudflare/tanlash/?kind=image&q=kurs").json()
    assert any(f["name"] == "logo.png" and "aksiya" in f["tags"] for f in j["files"])
    # studiya bo'limlari va media karta
    for tab in ("umumiy", "reja", "ssenariy", "tahlil", "mavzu", "hook"):
        assert c.get(f"/studiya/?tab={tab}").status_code == 200
    from apps.media_analysis.models import MediaFile, MediaAnalysis
    m = MediaFile.objects.create(business=b, original_name="v.mp4", kind="video", sha256="x", size=5, status="done", file="x.mp4")
    MediaAnalysis.objects.create(media=m, sha256="x", ai={"hook": {"text": "Xadicha", "strength": 4}, "visual_quality": 8, "cta": {"present": False, "clarity": 0}, "brand_fit": 2,
                                                         "strengths": ["a"], "improvements": ["b"], "scenes": [{"t": "0-3s", "what": "kirish", "attention": 7}], "platform_fit": {"shorts": 8}})
    h = c.get(f"/media/{m.pk}/").content.decode()
    assert "an-ring" in h and "Nima tuzatish kerak" in h and "Video sahna-sahna" in h and "Shorts" in h
    assert c.get("/havolalar/").status_code == 404
    assert "Dushanba" in c.get("/hisobotlar/").content.decode()


def test_autotime_calendar_drawer_and_competitor_alert(settings):
    c, u, b = _c(settings, "adm6")
    from apps.content.models import ContentItem
    from apps.connections.models import SocialAccount, Competitor
    from apps.content.models import ContentTarget
    acc = SocialAccount.objects.filter(business=b, platform="telegram").first()
    r = c.post("/kalendar/yangi/telegram/", {"title": "Avto1", "text": "Salom dunyo", "media_type": "text", "targets": [str(acc.pk)], "auto_time": "on"})
    assert r.status_code == 302
    a1 = ContentItem.objects.get(title="Avto1")
    assert a1.scheduled_at is not None
    r = c.post("/kalendar/yangi/telegram/", {"title": "Avto2", "text": "Salom dunyo 2", "media_type": "text", "targets": [str(acc.pk)], "auto_time": "on"})
    a2 = ContentItem.objects.get(title="Avto2")
    assert a2.scheduled_at and abs((a2.scheduled_at - a1.scheduled_at).total_seconds()) >= 3600   # to'qnashmaydi
    d = ContentItem.objects.create(business=b, title="Qoralama", text="x", media_type="text")
    ContentTarget.objects.create(item=d, account=acc)
    assert c.post(f"/kalendar/{d.pk}/avto-vaqt/").status_code == 302
    d.refresh_from_db(); assert d.scheduled_at
    d2 = ContentItem.objects.create(business=b, title="Qoralama2", text="y", media_type="text")
    ContentTarget.objects.create(item=d2, account=acc)
    assert c.post("/kalendar/avto-vaqt/").status_code == 302
    d2.refresh_from_db(); assert d2.scheduled_at
    html = c.get("/kalendar/").content.decode()
    assert 'id="calData"' in html and 'data-day=' in html and "cal_drawer.js" in html and 'id="dw"' in html
    # raqobatchi ogohlantirishi
    from datetime import timedelta
    from django.utils import timezone
    from apps.metrics.models import CompetitorPost
    from apps.metrics.collector import check_competitor_hits
    from apps.core.models import Notification
    comp = Competitor.objects.create(business=b, platform="instagram", handle="rival1", name="Rival")
    for i in range(8):
        CompetitorPost.objects.create(competitor=comp, business_id=b.pk, external_id=f"p{i}", views=1000, published_at=timezone.now() - timedelta(days=10 + i))
    CompetitorPost.objects.create(competitor=comp, business_id=b.pk, external_id="hit", views=5000, text="Aksiya!", media_type="reel", published_at=timezone.now() - timedelta(days=1))
    assert check_competitor_hits(comp) == 1
    assert Notification.objects.filter(type="competitor.hit").exists()
    assert check_competitor_hits(comp) == 0   # takror yuborilmaydi


def test_instagram_metrics_skip_unreadable_post(monkeypatch):
    from apps.connections.base import PlatformError
    from apps.connections.instagram import InstagramConnector
    c = InstagramConnector.__new__(InstagramConnector)
    def fake_get(path, **kw):
        if path == "BAD":
            raise PlatformError('{"error":{"message":"Unsupported get request. Object with ID \'BAD\' does not exist, cannot be loaded due to missing permissions"}}')
        return {"like_count": 3, "comments_count": 1, "media_product_type": "FEED"}
    monkeypatch.setattr(c, "_get", fake_get, raising=False)
    monkeypatch.setattr(c, "_insights", lambda mid, kind: {"views": 10}, raising=False)
    out = c.fetch_post_metrics(["OK1", "BAD", "OK2"])
    assert [m.external_id for m in out] == ["OK1", "OK2"]
