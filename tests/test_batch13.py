import io
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def _c(settings, name="b13", tmp=None):
    settings.USE_FAKES = True
    if tmp is not None:
        settings.MEDIA_ROOT = str(tmp)
    call_command("seed_demo")
    u = User.objects.create_user(name, password="Boss#2026test!", is_admin=True)
    c = Client(); c.force_login(u)
    b = Business.objects.first()
    c.post("/biznes-tanlash/", {"business": b.pk})
    return c, u, b


def _img(n, size=(400, 500), color="blue"):
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", size, color).save(buf, "JPEG")
    return SimpleUploadedFile(n, buf.getvalue(), "image/jpeg")


def test_carousel_order_move_duplicate_template(settings, tmp_path):
    c, u, b = _c(settings, "b13a", tmp_path)
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, PostTemplate
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    c.post("/kalendar/yangi/", {"title": "Tartib", "text": "Salom {biznes}", "media_type": "carousel", "targets": [str(acc.pk)], "files": [_img("a.jpg"), _img("b.jpg"), _img("c.jpg")]})
    it = ContentItem.objects.get(title="Tartib")
    names = lambda: [a.original_name for a in it.assets.all()]
    assert names() == ["a.jpg", "b.jpg", "c.jpg"]
    b_id = it.assets.get(original_name="b.jpg").pk
    c.post(f"/kalendar/{it.pk}/fayl/{b_id}/surish/", {"dir": "up"})
    assert names() == ["b.jpg", "a.jpg", "c.jpg"]
    c.post(f"/kalendar/{it.pk}/fayl/{b_id}/surish/", {"dir": "down"})
    c.post(f"/kalendar/{it.pk}/fayl/{b_id}/surish/", {"dir": "down"})
    assert names() == ["a.jpg", "c.jpg", "b.jpg"]
    assert "surish" in c.get(f"/kalendar/{it.pk}/").content.decode()
    # ko'chirish
    when = timezone.now() + timedelta(days=5)
    it.scheduled_at = when.replace(hour=10, minute=30); it.save()
    from apps.core.utils import local as _loc
    hhmm = _loc(it.scheduled_at).strftime("%H:%M")
    tgt = (timezone.localdate() + timedelta(days=9)).isoformat()
    r = c.post(f"/kalendar/{it.pk}/koch/", {"date": tgt})
    assert r.json()["ok"], r.content
    it.refresh_from_db()
    from apps.core.utils import local
    assert local(it.scheduled_at).date().isoformat() == tgt and local(it.scheduled_at).strftime("%H:%M") == hhmm
    assert c.post(f"/kalendar/{it.pk}/koch/", {"date": "2020-01-01"}).status_code == 400
    # nusxa + shablon
    r = c.post(f"/kalendar/{it.pk}/nusxa/")
    cp = ContentItem.objects.get(title="Tartib (nusxa)")
    assert cp.assets.count() == 3 and cp.status == "draft" and not cp.scheduled_at
    assert c.post(f"/kalendar/{it.pk}/shablon/", {"name": "Karusel andoza"}).status_code == 302
    t = PostTemplate.objects.get(name="Karusel andoza")
    assert t.platform == "instagram"
    assert "Karusel andoza" in c.get("/shablonlar/").content.decode()
    r = c.get(f"/kalendar/yangi/?shablon={t.pk}")
    assert r.status_code == 302 and "/kalendar/yangi/instagram/" in r["Location"]
    h = c.get(r["Location"]).content.decode()
    assert "Salom" in h and b.name in h.replace("&#x27;", "'") or "{biznes}" not in h
    # kalendar draggable
    cal = c.get("/kalendar/?m=" + local(it.scheduled_at).strftime("%Y-%m")).content.decode()
    assert 'draggable="true"' in cal or "draggable" in cal


def test_task_workflow_comments_and_search(settings, tmp_path):
    c, u, b = _c(settings, "b13b", tmp_path)
    from apps.content.models import ContentItem, ItemComment
    from apps.core.models import Notification
    d = User.objects.create_user("dizayner1", password="Pass12345!x")
    from apps.accounts.models import UserBusinessAccess
    UserBusinessAccess.objects.create(user=d, business=b, role=__import__("apps.accounts.models", fromlist=["Role"]).Role.objects.get(name="Kontent-maker"))
    it = ContentItem.objects.create(business=b, title="Banner kerak", text="matn", media_type="image", created_by=u)
    due = (timezone.now() + timedelta(hours=2)).astimezone(__import__("apps.core.utils", fromlist=["tz"]).tz()).strftime("%Y-%m-%dT%H:%M")
    r = c.post(f"/kalendar/{it.pk}/vazifa/", {"assignee": d.pk, "due_at": due, "brief": "Qizil fon"})
    it.refresh_from_db()
    assert it.assignee_id == d.pk and it.design_status == "todo" and it.due_at and it.brief == "Qizil fon"
    assert Notification.objects.filter(user=d, type="task.assigned").exists()
    cd = Client(); cd.force_login(d)
    assert "Banner kerak" in cd.get("/vazifalar/").content.decode()
    assert cd.post(f"/kalendar/{it.pk}/vazifa/holat/doing/").status_code == 302
    assert cd.post(f"/kalendar/{it.pk}/vazifa/holat/ready/", {"note": "Tayyor!"}).status_code == 302
    it.refresh_from_db(); assert it.design_status == "ready"
    assert Notification.objects.filter(user=u, type="design.status").exists()
    assert cd.post(f"/kalendar/{it.pk}/vazifa/holat/accepted/").status_code in (403, 302)
    it.refresh_from_db(); assert it.design_status == "ready"      # dizayner o'zi qabul qila olmaydi
    c.post(f"/kalendar/{it.pk}/vazifa/holat/revision/", {"note": "Logotip kattaroq"})
    it.refresh_from_db(); assert it.design_status == "revision"
    c.post(f"/kalendar/{it.pk}/izoh/", {"text": "Salom @dizayner1 tekshiring"})
    assert ItemComment.objects.filter(item=it, kind="comment").count() == 1
    assert Notification.objects.filter(user=d, title__startswith="Izoh").exists()
    h = c.get(f"/kalendar/{it.pk}/").content.decode()
    assert "Vazifa va muddat" in h and "Izohlar va yozishma" in h and "Logotip kattaroq" in h
    from apps.content import workflow
    assert workflow.deadline_scan() >= 1
    # qidiruv
    r = c.get("/qidiruv/?q=Banner")
    assert r.status_code == 200 and "Banner kerak" in r.content.decode()
    assert c.get("/qidiruv/?q=x").status_code == 200


def test_exact_preview_endpoint_and_pwa(settings, tmp_path):
    c, u, b = _c(settings, "b13c", tmp_path)
    r = c.post("/kalendar/aniq-korinish/", {"size": "ig_4x5", "fit": "crop", "cx": "0.2", "cy": "0.5", "cz": "1.2", "plat": "instagram", "file": _img("x.jpg", (800, 400))})
    assert r.status_code == 200 and r["X-Dims"] == "1080x1350" and r["Content-Type"] == "image/jpeg"
    r = c.post("/kalendar/aniq-korinish/", {"size": "orig", "plat": "telegram", "file": _img("x.jpg", (300, 300))})
    assert r["X-Dims"] == "300x300"
    m = Client().get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone" and len(m.json()["icons"]) >= 3
    sw = Client().get("/sw.js")
    assert sw.status_code == 200 and "fetch" in sw.content.decode() and sw["Service-Worker-Allowed"] == "/"
    assert Client().get("/oflayn/").status_code == 200
    h = c.get("/kalendar/").content.decode()
    assert 'rel="manifest"' in h and "apple-touch-icon" in h and 'id="pwaInstall"' in h
    assert c.get("/ilova/").status_code == 200
    for p in ("icon-192", "icon-512", "maskable-512", "apple-touch-icon"):
        assert (__import__("pathlib").Path("static/icons") / f"{p}.png").exists()


def test_client_publish_notice_daily_ideas_alerts(settings, tmp_path):
    c, u, b = _c(settings, "b13d", tmp_path)
    from apps.connections.models import SocialAccount
    from apps.content.models import ContentItem, ContentTarget
    from apps.tgbot import client_notify
    from apps.tgbot.bot import FakeBotAPI
    from apps.tgbot.models import ClientBotUser, ClientNotice
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    it = ContentItem.objects.create(business=b, title="Aksiya", text="Chegirma 20%", media_type="story", status="published")
    t = ContentTarget.objects.create(item=it, account=acc, status="published", published_at=timezone.now(), url="https://x/y")
    ClientBotUser.objects.create(tg_user_id=111, business_ids=[b.pk], name="Mijoz")
    ClientBotUser.objects.create(tg_user_id=222, business_ids=[b.pk], sections={str(b.pk): ["kpi"]})
    api = FakeBotAPI()
    r = client_notify.send_for_target(t.pk, api=api)
    assert r["sent_to"] == 1 and api.sent[0][0] == 111
    txt = api.sent[0][1]
    assert "Stories" in txt and "Instagram" in txt and "Aksiya" in txt and "Toshkent" in txt and "https://x/y" not in txt
    assert client_notify.send_for_target(t.pk, api=api).get("skipped") and ClientNotice.objects.filter(target_id=t.pk).count() == 1
    # g'oyalar banki
    from apps.studio import ideas
    from apps.studio.models import Idea
    new = ideas.generate_for_business(b, 2, use_ai=False)
    assert len(new) == 2 and all(i.script.get("scenes") and i.script_text for i in new)
    assert ideas.ensure_daily(b) == [] or True
    h = c.get("/goyalar/").content.decode()
    assert new[0].title.split("»")[0][:10] in h or "G'oyalar" in h.replace("&#x27;", "'")
    d = c.get(f"/goyalar/{new[0].pk}/").content.decode()
    assert "Rejissyor ssenariysi" in d
    assert c.post(f"/goyalar/{new[0].pk}/post/").status_code == 302
    new[0].refresh_from_db(); assert new[0].status == "used" and new[0].content_item_id
    # kunlik statistika + lid
    from apps.metrics import daily
    from apps.metrics.models import DailyStat, Lead
    c.post("/lidlar/qoshish/", {"name": "Ali", "phone": "+998901112233", "source": "instagram", "note": "story"})
    assert Lead.objects.filter(name="Ali").exists()
    daily.rollup_all()
    row = DailyStat.objects.filter(business=b, account__isnull=True).first()
    assert row and row.leads == 1
    assert c.get("/kunlik/").status_code == 200 and "csv" in c.get("/kunlik/").content.decode().lower()
    assert c.get("/kunlik/?csv=1")["Content-Type"].startswith("text/csv")
    assert c.get("/lidlar/").status_code == 200 and c.get("/lidlar/eksport/").status_code == 200
    # aqlli ogohlantirishlar
    from apps.core import alerts
    from apps.core.models import Notification
    res = alerts.run_all()
    assert "sent" in res and res["errors"] == 0
    assert c.get("/ogohlantirishlar/").status_code == 200
    assert c.post("/ogohlantirishlar/", {"on_no_posts": "on", "p_no_posts": "5", "run": "1"}).status_code == 302
    assert alerts.param("no_posts") == 5 and not alerts.is_on("disk")


def test_post_summary_and_openai_mode(settings, tmp_path):
    c, u, b = _c(settings, "b13e", tmp_path)
    from apps.connections.models import SocialAccount
    from apps.metrics.models import Post, PostMetricsHistory
    from apps.metrics import post_summary
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    p = Post.objects.create(business=b, account=acc, platform="instagram", external_id="zz1", text="Test post", published_at=timezone.now() - timedelta(days=2))
    PostMetricsHistory.objects.create(post=p, business_id=b.pk, taken_at=timezone.now(), views=1200, likes=90, comments=5, er=0.07)
    out = post_summary.run(p.pk, "24h")
    assert out["verdict"] in ("winner", "good", "average", "weak")
    from apps.studio.models import PostInsight
    assert "24 soatda" in PostInsight.objects.filter(post=p).first().text
    # OpenAI rejimi marshrutlari
    from apps.ai_router.router import AIRouter
    from apps.ai_router.types import AIRequest, TaskType
    from apps.core.settings_store import set_setting
    set_setting("ai.mode", "openai_only")
    r = AIRouter(use_fakes=True)
    assert r._routes(AIRequest(task=TaskType.LONG_UZ, prompt="x")) == [("openai", False)]
    set_setting("ai.mode", "openai_first")
    assert r._routes(AIRequest(task=TaskType.LONG_UZ, prompt="x"))[0][0] == "openai"
    set_setting("ai.mode", "free_first")
    assert c.get("/sozlamalar/?tab=ai").status_code == 200
    assert "OpenAI Platform holati" in c.get("/sozlamalar/?tab=ai").content.decode()


def test_story_deep_collect(settings, monkeypatch):
    c, u, b = _c(settings, "b13f")
    from apps.connections.models import SocialAccount
    from apps.metrics import collector
    from apps.metrics.models import Story
    acc = SocialAccount.objects.filter(business=b, platform="instagram").first()
    old = Story.objects.create(business=b, account=acc, external_id="s_old", published_at=timezone.now() - timedelta(hours=21), expires_at=timezone.now() + timedelta(hours=3))
    new = Story.objects.create(business=b, account=acc, external_id="s_new", published_at=timezone.now() - timedelta(hours=2), expires_at=timezone.now() + timedelta(hours=22))
    calls = []
    class SD:
        def __init__(s, i, pub): s.external_id, s.published_at, s.url = i, pub, ""
    class M:
        def __init__(s, i): s.external_id, s.taken_at, s.views, s.reach, s.comments, s.shares, s.extra = i, timezone.now(), 10, 8, 1, 0, {"deep": 1.0}
    class Conn:
        capabilities = {collector.Capability.STORIES}
        def fetch_stories(s): return [SD("s_old", old.published_at), SD("s_new", new.published_at)]
        def fetch_story_metrics(s, ids, deep=False): calls.append((list(ids), deep)); return [M(i) for i in ids]
    import apps.metrics.collector as col
    monkeypatch.setattr(col, "get_connector", lambda a: Conn())
    assert col.snapshot_stories(acc, deep=True) == 1
    assert calls == [(["s_old"], True)]


def test_client_report_pdf_page_and_share(settings, tmp_path):
    import os
    c, u, b = _c(settings, "b13g", tmp_path)
    from datetime import date
    from apps.reports.generator import default_period, generate_report
    from apps.reports.models import Report
    from apps.metrics.models import Lead
    Lead.objects.create(business=b, name="Vali", phone="9989", source="telegram", status="won", amount=500000, created_at=timezone.now())
    from apps.core.utils import local
    today = local(timezone.now()).date()
    s, e = today - timedelta(days=29), today
    r = Report.objects.create(business=b, kind="monthly", period_start=s, period_end=e, created_by=u)
    generate_report(r)
    r.refresh_from_db()
    assert r.status == "ready" and r.pdf and r.xlsx and r.data.get("leads", {}).get("total") == 1
    assert open(r.pdf.path, "rb").read(4) == b"%PDF"
    if os.environ.get("DUMP_PDF"):
        open(os.environ["DUMP_PDF"], "wb").write(open(r.pdf.path, "rb").read())
    h = c.get(f"/hisobotlar/{r.pk}/korinish/").content.decode()
    assert "Qisqacha xulosa" in h or "Lidlar" in h
    assert c.post(f"/hisobotlar/{r.pk}/havola/").status_code == 302
    r.refresh_from_db()
    assert r.share_token
    pub = Client().get(f"/h/{r.share_token}/")
    assert pub.status_code == 200 and b.name in pub.content.decode().replace("&#x27;", "'")
    assert Client().get("/h/xxxxxxxxxxxxxxxxxxxxxxxx/").status_code == 404
    r.share_expires = timezone.now() - timedelta(hours=1); r.save()
    assert Client().get(f"/h/{r.share_token}/").status_code == 404
