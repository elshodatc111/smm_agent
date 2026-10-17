"""Story uchun Jamendo musiqasi: ro'yxat, tanlash, video yig'ish, credit, sozlamalar tabi, o'chirilgan holat."""
import json
import subprocess

import pytest
from django.test import Client

from apps.core import settings_store as ss
from apps.stories import music, tgclient
from apps.stories.models import Story, StoryAccount
from tests.test_stories import cl, create, mk_accs, png, run_all  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    tgclient.FAKE_FAIL.clear()


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", path], capture_output=True, text=True).stdout
    return json.loads(out)


def test_list_endpoint_returns_ten(cl):
    d = cl.get("/stories/musiqa/royxat/").json()
    assert d["ok"] and len(d["items"]) == 10 and d["items"][0]["name"]
    assert len(cl.get("/stories/musiqa/royxat/?q=qo'shiq 3").json()["items"]) == 1


def test_list_disabled(cl):
    ss.set_setting("music.jamendo.enabled", False)
    assert cl.get("/stories/musiqa/royxat/").json()["ok"] is False


def test_story_with_music_builds_video_and_credit(cl):
    a = mk_accs(1)[0]
    r = create(cl, [a.pk], music_id="9002", music_start="5", music_len="12")
    assert r.status_code == 302, getattr(r, "content", b"")[:300]
    s = Story.objects.get()
    assert s.music_title == "Test qo'shiq 3" and s.music_len == 12 and s.music_start == 5 and s.music_video
    assert "Jamendo" in s.caption and s.caption.startswith("Salom")
    info = probe(s.music_video.path)
    types = {x["codec_type"] for x in info["streams"]}
    assert types == {"video", "audio"} and abs(float(info["format"]["duration"]) - 12) < 1
    v = next(x for x in info["streams"] if x["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)


def test_publish_uses_music_video_as_video(cl, monkeypatch):
    a = mk_accs(1)[0]
    create(cl, [a.pk], music_id="9001", music_len="10")
    seen = {}
    orig = tgclient.post_story

    def spy(sess, spec):
        seen.update(spec)
        return orig(sess, spec)
    monkeypatch.setattr(tgclient, "post_story", spy)
    run_all()
    assert seen["kind"] == "video" and seen["path"].endswith(".mp4") and "music" in seen["path"]
    assert Story.objects.get().status == "done"


def test_clamp_length_and_unknown_track(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk], music_id="9000", music_len="99")
    assert Story.objects.get().music_len == 30
    Story.objects.all().delete()
    r = create(cl, [a.pk], music_id="no-such")
    assert r.status_code == 200 and Story.objects.count() == 0


def test_no_credit_when_disabled(cl):
    ss.set_setting("music.jamendo.credit", False)
    a = mk_accs(1)[0]
    create(cl, [a.pk], music_id="9000", music_len="10")
    assert Story.objects.get().caption == "Salom"


def test_story_without_music_unchanged(cl):
    a = mk_accs(1)[0]
    create(cl, [a.pk])
    s = Story.objects.get()
    assert not s.music_video and s.caption == "Salom"


def test_settings_tab_only_jamendo(cl):
    r = cl.get("/sozlamalar/?tab=musiqa")
    html = r.content.decode()
    assert r.status_code == 200 and "client_id" in html and "meta.app_secret" not in html
    cl.post("/sozlamalar/?tab=musiqa", {"music__jamendo__client_id": "abc123secret", "music__jamendo__enabled": "on", "music__jamendo__count": "10", "music__jamendo__order": "popularity_week"})
    assert ss.get_secret("music.jamendo.client_id") == "abc123secret"
    assert "abc123secret" not in cl.get("/sozlamalar/?tab=musiqa").content.decode()
    r = cl.post("/sozlamalar/tekshir/jamendo/")
    assert r.status_code == 302 and "tab=musiqa" in r["Location"]


def test_new_page_shows_music_card(cl):
    assert "Fon musiqasi" in cl.get("/stories/yangi/").content.decode()
    ss.set_setting("music.jamendo.enabled", False)
    assert "Fon musiqasi" not in cl.get("/stories/yangi/").content.decode()


def test_license_filter():
    assert music.BAD_LICENSE.search("https://creativecommons.org/licenses/by-nc-nd/3.0/")
    assert music.BAD_LICENSE.search("https://creativecommons.org/licenses/by-nc/3.0/")
    assert music.BAD_LICENSE.search("https://creativecommons.org/licenses/by-nd/3.0/")
    assert not music.BAD_LICENSE.search("https://creativecommons.org/licenses/by-sa/3.0/")
    assert not music.BAD_LICENSE.search("https://creativecommons.org/licenses/by/3.0/")
