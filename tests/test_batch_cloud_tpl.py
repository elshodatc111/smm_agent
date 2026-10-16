import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.test_activity import _c

pytestmark = pytest.mark.django_db


def test_bucket_url_is_normalized_or_clear_error(settings):
    from apps.connections.base import PlatformError
    from apps.content import temphost
    from apps.core.settings_store import set_setting
    set_setting("r2.bucket", "https://abc123.r2.cloudflarestorage.com")
    with pytest.raises(PlatformError) as e:
        temphost.r2_bucket()
    assert "NOMI" in e.value.user_message_uz
    set_setting("r2.bucket", "https://abc123.r2.cloudflarestorage.com/smm-media")
    assert temphost.r2_bucket() == "smm-media"
    set_setting("r2.bucket", "smm-media")
    assert temphost.r2_bucket() == "smm-media"


def test_upload_pending_never_sticks(settings, monkeypatch, tmp_path):
    """Kutilmagan xato bo'lsa ham yozuv 'Xato' bo'ladi (abadiy 'Yuklanmoqda' emas)."""
    from apps.content import temphost
    from apps.content.models import TempObject
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x" * 100)
    o = TempObject.objects.create(key="k1.mp4", status="pending", size=100, local_path=str(f), filename="a.mp4")
    monkeypatch.setattr(temphost, "host_file", lambda *a, **k: (_ for _ in ()).throw(ValueError("Invalid bucket name")))
    o = temphost.upload_pending(o)
    assert o.status == "failed" and "bucket" in o.error.lower()


def test_chunked_upload_flow(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    c, u, b = _c(settings)
    data = b"0123456789" * 1000
    r = c.post("/cloudflare/yuklash/boshlash/", {"name": "v.mp4", "size": len(data)})
    assert r.status_code == 200, r.content
    oid = r.json()["id"]
    half = len(data) // 2
    assert c.post(f"/cloudflare/{oid}/bolak/", {"offset": 0, "chunk": SimpleUploadedFile("p", data[:half])}).json()["have"] == half
    # noto'g'ri tartib
    assert c.post(f"/cloudflare/{oid}/bolak/", {"offset": len(data), "chunk": SimpleUploadedFile("p", b"z")}).status_code == 409
    # to'liq emas
    assert c.post(f"/cloudflare/{oid}/tugatish/").status_code == 409
    # qayta yuborish (ustiga yozish) va tugatish
    c.post(f"/cloudflare/{oid}/bolak/", {"offset": 0, "chunk": SimpleUploadedFile("p", data[:half])})
    c.post(f"/cloudflare/{oid}/bolak/", {"offset": half, "chunk": SimpleUploadedFile("p", data[half:])})
    assert c.post(f"/cloudflare/{oid}/tugatish/").status_code == 200
    from apps.content.models import TempObject
    from apps.jobs.models import Job
    o = TempObject.objects.get(pk=oid)
    assert o.status == "pending" and Job.objects.filter(type="cloud_upload").exists()
    from apps.content.jobs import cloud_upload  # noqa: F401
    html = c.get("/cloudflare/").content.decode()
    assert "v.mp4" in html and "cl-bar" in html and "upList" in html
    assert c.post("/cloudflare/yuklash/boshlash/", {"name": "x.exe", "size": 5}).status_code == 400


def test_stop_and_delete_stuck_post(settings):
    c, u, b = _c(settings)
    c.post("/kalendar/yangi/telegram/", {"title": "Qotgan", "text": "salom", "media_type": "text", "scheduled_at": ""})
    from apps.content.models import ContentItem
    it = ContentItem.objects.get(title="Qotgan")
    ContentItem.objects.filter(pk=it.pk).update(status="publishing")
    from apps.content.models import ContentTarget
    ContentTarget.objects.filter(item=it).update(status="publishing")
    acts = [a["t"] for a in c.get(f"/kalendar/{it.pk}/").context["acts"]]
    assert "Nashrni to'xtatish" in acts and any("O'chirish" in a for a in acts)
    assert c.post(f"/kalendar/{it.pk}/toxtat/").status_code == 302
    it.refresh_from_db(); assert it.status == "failed"
    ContentItem.objects.filter(pk=it.pk).update(status="publishing")
    c.post(f"/kalendar/{it.pk}/ochir/")
    assert not ContentItem.objects.filter(pk=it.pk).exists() and ContentItem.all_objects.get(pk=it.pk).deleted_at


def test_template_crud(settings):
    c, u, b = _c(settings)
    from apps.content.models import PostTemplate
    r = c.post("/shablonlar/yangi/", {"name": "Dushanba", "platform": "telegram", "media_type": "video", "text": "{kun} aksiyasi", "weekday": "0", "time_hint": "10:00",
                                      "tg_buttons": "Sayt | https://example.com", "tg_cols": "2"})
    assert r.status_code == 302
    t = PostTemplate.objects.get(name="Dushanba")
    assert t.options["weekday"] == 0 and t.options["buttons"] and t.time_hint == "10:00"
    # platformaga mos bo'lmagan tur rad etiladi
    c.post("/shablonlar/yangi/", {"name": "Bad", "platform": "telegram", "media_type": "reel"})
    assert not PostTemplate.objects.filter(name="Bad").exists()
    c.post(f"/shablonlar/{t.pk}/saqlash/", {"name": "Dushanba 2", "platform": "telegram", "media_type": "text", "text": "yangi"})
    t.refresh_from_db(); assert t.name == "Dushanba 2" and "weekday" not in t.options
    assert "Dushanba 2" in c.get("/shablonlar/").content.decode()
    assert c.get("/shablonlar/yangi/").status_code == 200 and c.get(f"/shablonlar/{t.pk}/tahrir/").status_code == 200
    # shablondan forma
    assert c.get(f"/kalendar/yangi/telegram/?shablon={t.pk}").status_code == 200
    c.post(f"/shablonlar/{t.pk}/ochir/")
    assert not PostTemplate.objects.filter(pk=t.pk).exists()
