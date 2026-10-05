"""Provayder implementatsiyalari: YouTube Data API (kalit), ScrapeCreators, t.me ochiq, Fake."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from apps.connections.base import (AuthError, NotFoundError, Platform, PlatformError)
from apps.connections.http import request
from apps.connections.public_tme import PublicChannelScraper
from apps.core.settings_store import get_secret, get_setting

from .base import Cost, DataKind, DataRequest, DataResponse, ProviderStatus

YT = "https://www.googleapis.com/youtube/v3"
K = DataKind


def _now():
    return datetime.now(timezone.utc)


def _cache_param(sec: int) -> str:
    """ScrapeCreators faqat 1d, 3d, 7d, 14d, 30d qabul qiladi: soniyani eng yaqin yuqori qiymatga o'giramiz."""
    for days in (1, 3, 7, 14, 30):
        if sec <= days * 86400:
            return f"{days}d"
    return "30d"


class YouTubeDataAPIProvider:
    name = "youtube_data_api"
    supports = {Platform.YOUTUBE: {K.PROFILE, K.VIDEO_LIST, K.COMMENTS}}
    COSTS = {K.PROFILE: 1, K.VIDEO_LIST: 2, K.COMMENTS: 1}  # list=1; video ro'yxati = playlistItems + videos

    def estimate_cost(self, platform, kind, count):
        return Cost("quota_units", float(self.COSTS.get(kind, 1)))

    def _get(self, path, **p):
        key = get_secret("youtube.api_key")
        if not key:
            raise AuthError("youtube.api_key yo'q", user_message_uz="YouTube Data API kaliti kiritilmagan.")
        return request("GET", f"{YT}/{path}", key="yt-pub", params={**p, "key": key}).json()

    def _channel(self, target: str) -> dict:
        t = target.strip()
        if t.startswith("UC") and len(t) > 20:
            j = self._get("channels", part="snippet,statistics,contentDetails", id=t)
        else:
            j = self._get("channels", part="snippet,statistics,contentDetails", forHandle=t if t.startswith("@") else "@" + t.split("/")[-1].lstrip("@"))
        if not j.get("items"):
            raise NotFoundError(f"kanal topilmadi: {target}")
        return j["items"][0]

    def fetch(self, req: DataRequest) -> DataResponse:
        cost = self.estimate_cost(req.platform, req.kind, req.limit)
        if req.kind == K.PROFILE:
            ch = self._channel(req.target)
            s = ch["statistics"]
            data = {"id": ch["id"], "title": ch["snippet"]["title"], "followers": int(s.get("subscriberCount", 0)),
                    "views": int(s.get("viewCount", 0)), "posts_count": int(s.get("videoCount", 0))}
        elif req.kind == K.VIDEO_LIST:
            ch = self._channel(req.target)
            pl = ch["contentDetails"]["relatedPlaylists"]["uploads"]
            items = self._get("playlistItems", part="contentDetails", playlistId=pl, maxResults=min(req.limit, 50))
            ids = [i["contentDetails"]["videoId"] for i in items.get("items", [])]
            vids = self._get("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []) if ids else []
            data = [{"id": v["id"], "title": v["snippet"]["title"], "published_at": v["snippet"]["publishedAt"],
                     "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0)),
                     "comments": int(v["statistics"].get("commentCount", 0)), "duration": v["contentDetails"]["duration"]} for v in vids]
        else:
            j = self._get("commentThreads", part="snippet", videoId=req.target, maxResults=min(req.limit, 100))
            data = [{"id": t["id"], "text": t["snippet"]["topLevelComment"]["snippet"]["textDisplay"]} for t in j.get("items", [])]
        return DataResponse(self.name, data, cost, False, _now())

    def status(self) -> ProviderStatus:
        from .quota import youtube_quota_used
        lim = float(get_setting("providers.youtube_data_api.daily_quota", 10000))
        used = youtube_quota_used()
        return ProviderStatus(bool(get_secret("youtube.api_key")), lim - used, "quota_units")


class ScrapeCreatorsProvider:
    """https://scrapecreators.com — endpointlar hujjatga qarab tekshiring (docs/setup/05)."""
    name = "scrapecreators"
    BASE = "https://api.scrapecreators.com"
    supports = {
        Platform.YOUTUBE: {K.PROFILE, K.VIDEO_LIST, K.COMMENTS, K.TRANSCRIPT},
        Platform.INSTAGRAM: {K.PROFILE, K.POSTS},
        Platform.TELEGRAM: set(),
    }
    ENDPOINTS = {
        (Platform.YOUTUBE, K.PROFILE): "/v1/youtube/channel",
        (Platform.YOUTUBE, K.VIDEO_LIST): "/v1/youtube/channel-videos",
        (Platform.YOUTUBE, K.COMMENTS): "/v1/youtube/video/comments",
        (Platform.YOUTUBE, K.TRANSCRIPT): "/v1/youtube/video/transcript",
        (Platform.INSTAGRAM, K.PROFILE): "/v1/instagram/profile",
        (Platform.INSTAGRAM, K.POSTS): "/v2/instagram/user/posts",
    }
    PARAM = {K.PROFILE: "handle", K.VIDEO_LIST: "handle", K.POSTS: "handle", K.COMMENTS: "url", K.TRANSCRIPT: "url"}
    CREDITS = {K.PROFILE: 1, K.VIDEO_LIST: 1, K.POSTS: 1, K.COMMENTS: 1, K.TRANSCRIPT: 1}

    def estimate_cost(self, platform, kind, count):
        pages = max(1, -(-count // 30)) if kind in (K.VIDEO_LIST, K.POSTS, K.COMMENTS) else 1
        return Cost("credits", float(self.CREDITS.get(kind, 1) * pages))

    def fetch(self, req: DataRequest) -> DataResponse:
        key = get_secret("scrapecreators.api_key")
        if not key:
            raise AuthError("scrapecreators.api_key yo'q", user_message_uz="ScrapeCreators API kaliti kiritilmagan.")
        path = self.ENDPOINTS[(req.platform, req.kind)]
        p = {self.PARAM[req.kind]: req.target.lstrip("@") if self.PARAM[req.kind] == "handle" else req.target}
        age = req.cache_max_age_sec or int(get_setting("scrapecreators.cache_max_age_sec", 21600))
        if age:
            p["cache_max_age"] = _cache_param(age)  # keshdan javob kredit sarflamaydi
        r = request("GET", self.BASE + path, key="scrapecreators", min_interval=0.5, jitter=0.5,
                    headers={"x-api-key": key}, params=p)
        j = r.json()
        remaining = j.get("credits_remaining") if isinstance(j, dict) else None
        cached = bool(r.headers.get("x-cache-hit") or (isinstance(j, dict) and j.get("cached")))
        self._last_remaining = remaining
        return DataResponse(self.name, j, Cost("credits", 0.0 if cached else self.estimate_cost(req.platform, req.kind, req.limit).amount),
                            cached, _now())

    def status(self) -> ProviderStatus:
        key = get_secret("scrapecreators.api_key")
        if not key:
            return ProviderStatus(False, None, "credits", "Kalit yo'q")
        try:
            j = request("GET", self.BASE + "/v1/credit-balance", key="scrapecreators", headers={"x-api-key": key}).json()
            return ProviderStatus(True, float(j.get("creditCount", j.get("credits", 0))), "credits")
        except PlatformError as e:
            return ProviderStatus(False, None, "credits", str(e)[:100])


class TmePublicProvider:
    name = "tme_public"
    supports = {Platform.TELEGRAM: {K.PROFILE, K.POSTS}}

    def estimate_cost(self, platform, kind, count):
        return Cost("quota_units", 0.0)

    def fetch(self, req: DataRequest) -> DataResponse:
        sc = PublicChannelScraper(req.target)
        if req.kind == K.PROFILE:
            st = sc.fetch_account_stats()
            data = {"followers": st.followers}
        else:
            page = sc.fetch_posts(_now() - timedelta(days=30), req.cursor, max_pages=2)
            data = [{"id": p.external_id, "text": p.text, "published_at": p.published_at.isoformat(),
                     "views": (p.raw or {}).get("views"), "type": str(p.media_type)} for p in page.items]
        return DataResponse(self.name, data, Cost("quota_units", 0.0), False, _now())

    def status(self) -> ProviderStatus:
        return ProviderStatus(True, None, "", "Ochiq sahifa (limitsiz, sekin)")


class FakeProvider:
    """Deterministik demo; `fail_with` orqali testlarda xato imitatsiyasi."""
    supports = {p: set(DataKind) for p in Platform}

    def __init__(self, name="fake", unit="quota_units", cost=1.0):
        self.name, self.unit, self.cost, self.fail_with, self.calls = name, unit, cost, None, 0

    def estimate_cost(self, platform, kind, count):
        return Cost(self.unit, self.cost)

    def fetch(self, req):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        r = random.Random(f"{req.target}{req.kind}")
        if req.kind == DataKind.PROFILE:
            data = {"followers": r.randint(1000, 90000), "title": req.target, "posts_count": r.randint(20, 400)}
        else:
            data = [{"id": f"{req.target}-{i}", "text": f"Raqobatchi post {i}", "views": r.randint(100, 9000),
                     "likes": r.randint(5, 500), "published_at": (_now() - timedelta(days=i)).isoformat()} for i in range(req.limit)]
        return DataResponse(self.name, data, Cost(self.unit, self.cost), False, _now())

    def status(self):
        return ProviderStatus(True, 100.0, self.unit)
