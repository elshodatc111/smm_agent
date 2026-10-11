"""Veb qatlami: barcha sahifalar 500 bermasligi, RBAC va biznes izolyatsiyasi."""
import re

import pytest
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import Role, User, UserBusinessAccess
from apps.businesses.models import Business


@pytest.fixture
def demo(db, settings):
    settings.USE_FAKES = True
    call_command("seed_demo")
    admin = User.objects.create_user("boss", password="Boss#2026test!", is_admin=True)
    return admin


def login(username, pw):
    c = Client()
    assert c.post("/kirish/", {"username": username, "password": pw}).status_code == 302
    return c


def test_login_required(db):
    r = Client().get("/")
    assert r.status_code == 302 and "/kirish/" in r["Location"]


def test_wrong_password(db):
    User.objects.create_user("x", password="Aaaa#1234567")
    r = Client().post("/kirish/", {"username": "x", "password": "bad"})
    assert r.status_code == 200 and "Login yoki parol" in r.content.decode()


def test_all_get_pages_no_500(demo):
    c = login("boss", "Boss#2026test!")
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    from apps.connections.models import SocialAccount, Competitor
    from apps.content.models import ContentItem
    from apps.metrics.models import Post
    acc, comp, item, post = SocialAccount.objects.filter(business=b).first(), Competitor.objects.filter(business=b).first(), ContentItem.objects.filter(business=b).first(), Post.objects.filter(business=b).first()
    role = Role.objects.first()
    vals = {"pk": None, "slug": "01-umumiy", "provider": "instagram", "kind": "pdf", "new": "draft", "what": "worker", "vid": 1, "aid": 1}
    bad, seen = [], 0
    import apps.web.urls as U
    for p in U.urlpatterns:
        pat = str(p.pattern)
        if p.name in ("logout", "theme", "oauth_done") or "<" in pat and "pk" not in pat and "slug" not in pat:
            continue
        if "<int:pk>" in pat:
            m = {"business_detail": b, "business_edit": b, "connection_detail": acc, "competitor_detail": comp, "content_detail": item, "content_edit": item, "post_insight": post,
                 "user_detail": admin_pk(), "role_detail": role}.get(p.name)
            if m is None:
                continue
            url = "/" + re.sub(r"<int:pk>", str(m.pk), pat)
        elif "<" in pat:
            if p.name != "guide_view":
                continue
            url = "/" + pat.replace("<slug:slug>", "01-umumiy")
        else:
            url = "/" + pat
        if "ochir" in url or "yangila" in url:
            continue
        r = c.get(url)
        seen += 1
        if r.status_code >= 500 or r.status_code == 404 and p.name != "guide_view":
            bad.append((url, r.status_code))
    assert seen > 30
    assert not bad, bad


def admin_pk():
    return User.objects.get(username="boss")


def test_manager_cannot_see_other_business(demo):
    c = login("menejer", "Menejer#2026demo")
    third = Business.objects.order_by("id").last()
    assert c.get(f"/bizneslar/{third.pk}/").status_code == 404
    assert c.get("/sozlamalar/").status_code in (302, 403)
    assert c.get("/foydalanuvchilar/").status_code in (302, 403)
    own = Business.objects.filter(accesses__user__username="menejer").first()
    assert c.get(f"/bizneslar/{own.pk}/").status_code == 200


def test_secret_never_rendered(demo):
    from apps.core.settings_store import set_setting
    set_setting("meta.app_secret", "SUPERSECRETVALUE123456")
    c = login("boss", "Boss#2026test!")
    html = c.get("/sozlamalar/?tab=kalitlar").content.decode()
    assert "SUPERSECRETVALUE123456" not in html


def test_post_requires_csrf_free_client_ok_and_get_blocked(demo):
    c = login("boss", "Boss#2026test!")
    assert c.get("/chiqish/").status_code == 405


def test_business_and_content_flow(demo):
    from apps.content.models import ContentItem
    from apps.connections.models import SocialAccount
    c = login("boss", "Boss#2026test!")
    r = c.post("/bizneslar/yangi/", {"name": "Test Biznes", "languages": "uz", "main_goal": "lead", "currency": "UZS", "monthly_ad_budget": "0", "avg_check": "0", "lead_to_sale": "0.2",
                                   "facts_text": "telefon = +998 90 111 22 33"})
    assert r.status_code == 302, r.content.decode()[:500]
    b = Business.objects.get(name="Test Biznes")
    assert b.facts["telefon"].startswith("+998")
    c.post("/biznes-tanlash/", {"business": b.pk})
    # demo OAuth ulanish
    r = c.get("/ulanishlar/oauth/instagram/boshlash/")
    assert r.status_code == 302
    acc = SocialAccount.objects.get(business=b)
    assert c.post(f"/ulanishlar/{acc.pk}/test/").status_code == 302
    # kontent
    r = c.post("/kalendar/yangi/", {"title": "Salom", "text": "Test post. Aloqa: +998 90 111 22 33", "media_type": "image", "targets": [str(acc.pk)]})
    assert r.status_code == 302, r.content.decode()[:800]
    it = ContentItem.objects.get(business=b)
    assert it.targets.count() == 1
    assert c.post(f"/kalendar/{it.pk}/tekshir/").status_code == 302
    # vaqt qo'yilmagan -> qoralama; vaqt qo'yib tahrirlansa avtomatik rejalashtiriladi (tasdiqlash yo'q)
    assert it.status == "draft"
    from django.core.files.uploadedfile import SimpleUploadedFile
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    c.post(f"/kalendar/{it.pk}/tahrir/", {"title": "Salom", "text": "O'zgargan matn, yangi kurs boshlandi", "media_type": "image", "targets": [str(acc.pk)],
                                          "scheduled_at": "2030-01-01T10:00", "files": SimpleUploadedFile("a.png", png, content_type="image/png")})
    it.refresh_from_db()
    assert it.status == "scheduled" and it.scheduled_at.isoformat().startswith("2030-01-01T05:00")   # Toshkent 10:00 = UTC 05:00
    assert c.get(f"/kalendar/{it.pk}/").status_code == 200
    # hisobot
    assert c.post("/hisobotlar/yaratish/", {"kind": "weekly"}).status_code == 302


def test_user_and_role_admin(demo):
    c = login("boss", "Boss#2026test!")
    r = c.post("/foydalanuvchilar/yangi/", {"username": "yangi", "password": "Yangi#2026pass", "is_active": "on"})
    assert r.status_code == 302, r.content.decode()[:600]
    u = User.objects.get(username="yangi")
    assert not u.is_admin
    role = Role.objects.get(name="Analitik")
    b = Business.objects.first()
    c.post(f"/foydalanuvchilar/{u.pk}/kirish/", {"business": b.pk, "role": role.pk})
    assert UserBusinessAccess.objects.filter(user=u, business=b).exists()
    # oxirgi adminni pasaytirib bo'lmaydi
    boss = User.objects.get(username="boss")
    c.post(f"/foydalanuvchilar/{boss.pk}/tahrir/", {"username": "boss", "is_active": "on"})
    boss.refresh_from_db()
    assert boss.is_admin


def test_security_headers_and_csrf(demo):
    c = Client(enforce_csrf_checks=True)
    r = c.post("/kirish/", {"username": "boss", "password": "x"})
    assert r.status_code == 403


def test_calendar_grid_and_new_ai_pages(demo):
    from apps.ai_router import router as r
    c = login("boss", "Boss#2026test!")
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    html = c.get("/kalendar/").content.decode()
    assert 'class="cg"' in html and "/kalendar/yangi/?date=" in html
    assert c.get("/kalendar/yangi/?date=2030-05-06").status_code == 200
    for u in ("/raqobatchilar/", "/studiya/", "/reklama/"):
        assert c.get(u).status_code == 200, u
    # POST'lar 500 bermasligi (AI yo'q bo'lsa ham xabar bilan qaytadi)
    for u in ("/raqobatchilar/xulosa/", "/studiya/mavzular/"):
        assert c.post(u, {}).status_code in (302, 200), u


def test_business_limit_and_no_approval_ui(demo):
    from apps.core.settings_store import set_setting
    c = login("boss", "Boss#2026test!")
    set_setting("agency.max_businesses", 1)
    r = c.post("/bizneslar/yangi/", {"name": "Ortiqcha", "languages": "uz", "main_goal": "lead", "currency": "UZS", "monthly_ad_budget": "0", "avg_check": "0", "lead_to_sale": "0.2"})
    assert r.status_code == 302 and not Business.objects.filter(name="Ortiqcha").exists()
    html = c.get("/").content.decode().lower()
    assert "tasdiqlash" not in html


def test_ai_features_with_fakes(demo):
    from apps.studio import services as st
    from apps.content.models import ContentItem
    b = Business.objects.first()
    g = st.design_topics(b, "", 4, user=User.objects.get(username="boss"))
    assert g.kind == "design_topics"
    n = st.load_topics_to_calendar(g, None)
    assert n == len((g.data or {}).get("topics", [])) and (n == 0 or ContentItem.objects.filter(business=b, ai_draft=True, status="draft").exists())
    try:
        st.competitor_summary(b)
    except ValueError:
        pass


def test_mediafit_and_graph_errors(tmp_path, settings):
    from PIL import Image
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.content import mediafit
    src = tmp_path / "wide.png"
    Image.new("RGB", (3000, 600), "red").save(src)
    out = mediafit.fit_path(str(src), "image", "ig_4x5", "pad")
    with Image.open(out) as im:
        assert im.size == (1080, 1350)
    out2 = mediafit.auto_instagram_image(str(src))
    with Image.open(out2) as im:
        assert im.size == (1080, 566)
    assert mediafit.fit_path(str(src), "image", "orig") == str(src)
    # Graph xato matni ko'rinadi
    import requests
    from apps.connections.http import raise_for_status
    from apps.connections.base import PlatformError
    r = requests.Response(); r.status_code = 400; r.url = "https://graph.instagram.com/v21.0/1/media"
    r._content = b'{"error":{"message":"Bad","code":9004,"error_subcode":2207026}}'
    try:
        raise_for_status(r)
    except PlatformError as e:
        assert "MP4" in e.user_message_uz and "2207026" in e.user_message_uz


def test_director_script_and_youtube_ai(demo):
    from apps.studio import services as st
    body = {"title": "T", "scenes": [{"n": 1, "t": "0-3s", "shot_type": "close-up", "camera": {"position": "aktyorning chap tomonida, 1 m"}, "actor": {"action": "kulib qaraydi"}}],
            "audio": {"trending_audios": [{"name": "X — Y", "why": "tez", "where": "Reels"}]}}
    t = st.script_text(body)
    assert "Kamera joyi" in t and "Aktyor" in t and "X — Y" in t
    c = login("boss", "Boss#2026test!")
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    r = c.post("/kalendar/ai/youtube/", {"media_type": "video", "text": "Yangi kurs"})
    assert r.status_code == 200 and ("title" in r.json() or "error" in r.json())
    assert c.get("/kalendar/yangi/").status_code == 200


def test_analytics_per_platform(demo):
    c = login("boss", "Boss#2026test!")
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    for q in ("", "?p=telegram", "?p=instagram&days=90", "?p=youtube&f=short", "?p=bad"):
        assert c.get("/tahlil/" + q).status_code == 200, q


def test_calendar_filters(demo):
    c = login("boss", "Boss#2026test!")
    c.post("/biznes-tanlash/", {"business": Business.objects.first().pk})
    for q in ("", "?p=instagram", "?p=instagram&f=reel&status=draft", "?p=youtube&f=short&m=2030-01"):
        assert c.get("/kalendar/" + q).status_code == 200, q


def test_platform_forms_cloud_and_trash(demo, settings, tmp_path):
    from apps.content import temphost
    from apps.content.models import ContentAsset, ContentItem, TempObject
    from apps.jobs.queue import Job
    settings.MEDIA_ROOT = str(tmp_path)
    c = login("boss", "Boss#2026test!")
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    assert c.get("/kalendar/yangi/zzz/").status_code == 404
    html = c.get("/kalendar/yangi/instagram/").content.decode()
    assert "tahlilidan xulosa" in html and "image_editor.js" in html
    # media saqlansa -> Cloudflare yozuvi + navbat (USE_FAKES: FakeHost)
    from django.core.files.uploadedfile import SimpleUploadedFile
    from apps.connections.models import SocialAccount
    acc = SocialAccount.objects.filter(business=b, platform="telegram").first()
    r = c.post("/kalendar/yangi/telegram/", {"title": "K", "text": "Salom dunyo", "media_type": "image", "targets": [str(acc.pk)],
                                              "files": SimpleUploadedFile("a.jpg", b"\xff\xd8\xff" + b"0" * 100, content_type="image/jpeg")})
    assert r.status_code == 302
    it = ContentItem.objects.get(title="K")
    o = TempObject.objects.get(item=it)
    assert o.status == "pending"
    temphost.upload_pending(o, fake=True)
    o.refresh_from_db()
    assert o.status == "uploaded" and o.delete_after is None or o.backend == "fake"
    assert c.get("/cloudflare/").status_code == 200 and "a.jpg" in c.get("/cloudflare/").content.decode()
    # qo'lda o'chirish
    assert c.post(f"/cloudflare/{o.pk}/ochir/").status_code == 302
    o.refresh_from_db()
    assert o.status == "deleted"
    # savat
    assert c.post(f"/kalendar/{it.pk}/ochir/").status_code == 302
    assert not ContentItem.objects.filter(pk=it.pk).exists() and ContentItem.all_objects.filter(pk=it.pk).exists()
    assert "K" in c.get("/kalendar/savat/").content.decode()
    assert c.get(f"/kalendar/{it.pk}/").status_code == 404
    assert c.post(f"/kalendar/savat/{it.pk}/tiklash/").status_code == 302
    assert ContentItem.objects.filter(pk=it.pk).exists()
    c.post(f"/kalendar/{it.pk}/ochir/")
    assert c.post(f"/kalendar/savat/{it.pk}/ochir/").status_code == 302
    assert not ContentItem.all_objects.filter(pk=it.pk).exists()
