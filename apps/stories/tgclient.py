"""Telegram Stories uchun Telethon qatlami. Faqat story qo'yish va ko'rishlarni o'qish (xabar yuborish, a'zo qo'shish yo'q).

USE_FAKES=True (testlar) da tarmoqqa chiqmaydi: FAKE_FAIL = {account_pk: 'premium'|'flood'|...} xatoni simulyatsiya qiladi."""
from __future__ import annotations

import random
import shutil
import subprocess

from django.conf import settings

from apps.connections import telethon_login as tl

FAKE_FAIL: dict[int, str] = {}
_FAKE_SEQ = {"n": 100}

MSG = {
    "premium": "Bu akkaunt Telegram Premium emas: tanlangan imkoniyat (uzun sarlavha, 48 soat, havola stikeri va h.k.) Premium talab qiladi.",
    "limit": "Story limiti tugagan (kunlik/haftalik/oylik). Bir ozdan keyin qayta urinib ko'ring.",
    "flood": "Telegram vaqtincha kutishni talab qildi (FloodWait).",
    "media": "Fayl story uchun yaroqsiz (format/o'lcham/uzunlik). Video: mp4, 9:16, 60 soniyagacha tavsiya etiladi.",
    "auth": "Akkaunt sessiyasi bekor bo'lgan. Akkauntni qayta ulang.",
    "other": "Noma'lum xato.",
}


class StoryError(Exception):
    def __init__(self, code: str, detail: str = "", wait: int = 0):
        self.code, self.detail, self.wait = code, detail, wait
        super().__init__(f"{code}: {detail}")

    @property
    def message_uz(self) -> str:
        base = MSG.get(self.code, MSG["other"])
        return f"{base} ({self.detail[:120]})" if self.detail and self.code in ("other", "media") else base


def classify(exc: Exception) -> StoryError:
    """Telethon xatosini bizning kodlarimizga aylantiradi (klass nomi bo'yicha — import xatosiz)."""
    name, text = type(exc).__name__, str(exc).upper()
    wait = int(getattr(exc, "seconds", 0) or 0)
    if "FloodWait" in name:
        return StoryError("flood", str(exc), wait)
    if "PREMIUM" in text or "PREMIUM" in name.upper():
        return StoryError("premium", str(exc))
    if any(k in name for k in ("StoriesTooMuch", "StorySendFlood", "StoriesNeverCreated")) or "STORIES_TOO_MUCH" in text or "STORY_SEND_FLOOD" in text:
        return StoryError("limit", str(exc))
    if any(k in name for k in ("AuthKey", "SessionRevoked", "SessionExpired", "UserDeactivated", "Unauthorized")):
        return StoryError("auth", str(exc))
    if any(k in name for k in ("Media", "Photo", "Video", "Document", "File", "StoryPeriod")) or "MEDIA" in text or "PERIOD" in text:
        return StoryError("media", str(exc))
    return StoryError("other", f"{name}: {exc}")


def _probe(path: str) -> tuple[float, int, int]:
    """(davomiylik, eni, bo'yi) — ffprobe bo'lsa; bo'lmasa taxminiy."""
    if shutil.which("ffprobe"):
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                "-of", "csv=p=0:s=,", path], capture_output=True, text=True, timeout=60)
            lines = [x for x in r.stdout.strip().splitlines() if x]
            w, h = (int(x) for x in lines[0].split(",")[:2])
            return float(lines[1]), w, h
        except Exception:  # noqa: BLE001
            pass
    return 10.0, 1080, 1920


def _fake() -> bool:
    return bool(getattr(settings, "USE_FAKES", False))


def account_info(session: str) -> dict:
    """{'id', 'username', 'premium', 'name'} — ulanishdan keyin va holatni tekshirishda."""
    if _fake():
        return {"id": 777, "username": "fake_user", "premium": False, "name": "Fake"}
    client, loop = tl._mk(session)
    try:
        loop.run_until_complete(client.connect())
        me = loop.run_until_complete(client.get_me())
        if not me:
            raise StoryError("auth", "avtorizatsiya yo'q")
        return {"id": me.id, "username": me.username or "", "premium": bool(getattr(me, "premium", False)),
                "name": " ".join(x for x in (me.first_name, me.last_name) if x)}
    except StoryError:
        raise
    except Exception as e:  # noqa: BLE001
        raise classify(e) from e
    finally:
        tl._close(client, loop)


def _areas(spec: dict):
    from telethon.tl import types as T

    def box(y):
        return T.MediaAreaCoordinates(x=50.0, y=y, w=70.0, h=9.0, rotation=0.0)
    out = []
    if spec.get("link_url"):
        out.append(T.MediaAreaUrl(coordinates=box(86.0), url=spec["link_url"]))
    if spec.get("reaction"):
        out.append(T.MediaAreaSuggestedReaction(coordinates=T.MediaAreaCoordinates(x=50.0, y=60.0, w=22.0, h=12.0, rotation=0.0),
                                                reaction=T.ReactionEmoji(emoticon=spec["reaction"])))
    if spec.get("lat") is not None and spec.get("lon") is not None:
        out.append(T.MediaAreaGeoPoint(coordinates=box(12.0), geo=T.GeoPoint(lat=float(spec["lat"]), long=float(spec["lon"]), access_hash=0)))
    return out


def post_story(session: str, spec: dict) -> dict:
    """spec: path, kind, caption, period, privacy, pinned, noforwards, link_url, reaction, lat, lon. -> {'id': int}"""
    if _fake():
        code = FAKE_FAIL.get(spec.get("account_pk"))
        if code:
            raise StoryError(code, "fake", wait=120 if code == "flood" else 0)
        _FAKE_SEQ["n"] += 1
        return {"id": _FAKE_SEQ["n"]}
    from telethon.extensions import html as thtml
    from telethon.tl import functions as F
    from telethon.tl import types as T
    client, loop = tl._mk(session)
    run = loop.run_until_complete
    try:
        run(client.connect())
        peer = T.InputPeerSelf()
        can = run(client(F.stories.CanSendStoryRequest(peer=peer)))
        if can is False or getattr(can, "count_remains", 1) == 0:
            raise StoryError("limit", "hozir story qo'yib bo'lmaydi")
        up = run(client.upload_file(spec["path"]))
        if spec["kind"] == "video":
            dur, w, h = _probe(spec["path"])
            media = T.InputMediaUploadedDocument(file=up, mime_type="video/mp4", attributes=[T.DocumentAttributeVideo(
                duration=dur, w=w, h=h, supports_streaming=True)])
        else:
            media = T.InputMediaUploadedPhoto(file=up)
        priv = {"all": [T.InputPrivacyValueAllowAll()], "contacts": [T.InputPrivacyValueAllowContacts()],
                "close": [T.InputPrivacyValueAllowCloseFriends()]}[spec.get("privacy", "all")]
        text, ents = thtml.parse(spec["caption"]) if spec.get("caption") else ("", [])
        areas = _areas(spec)
        res = run(client(F.stories.SendStoryRequest(
            peer=peer, media=media, privacy_rules=priv, pinned=bool(spec.get("pinned")) or None, noforwards=bool(spec.get("noforwards")) or None,
            media_areas=areas or None, caption=text or None, entities=ents or None, period=int(spec.get("period") or 86400),
            random_id=random.randrange(1 << 62))))
        sid = None
        for u in getattr(res, "updates", []) or []:
            if type(u).__name__ == "UpdateStory":
                sid = u.story.id
        if sid is None:
            raise StoryError("other", "Telegram story ID qaytarmadi")
        return {"id": sid}
    except StoryError:
        raise
    except Exception as e:  # noqa: BLE001
        raise classify(e) from e
    finally:
        tl._close(client, loop)


def fetch_stats(session: str, story_id: int, account_pk: int | None = None) -> dict:
    """{'views','forwards','reactions'}"""
    if _fake():
        return {"views": 10 * (story_id % 50 + 1), "forwards": story_id % 3, "reactions": story_id % 5}
    from telethon.tl import functions as F
    from telethon.tl import types as T
    client, loop = tl._mk(session)
    try:
        loop.run_until_complete(client.connect())
        r = loop.run_until_complete(client(F.stories.GetStoriesViewsRequest(peer=T.InputPeerSelf(), id=[int(story_id)])))
        v = r.views[0] if getattr(r, "views", None) else None
        if v is None:
            return {"views": 0, "forwards": 0, "reactions": 0}
        return {"views": int(v.views_count or 0), "forwards": int(getattr(v, "forwards_count", 0) or 0), "reactions": int(getattr(v, "reactions_count", 0) or 0)}
    except Exception as e:  # noqa: BLE001
        raise classify(e) from e
    finally:
        tl._close(client, loop)
