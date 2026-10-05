"""YouTube connector: Data API v3 + Analytics + Upload (OAuth 2.0, login/parol yo'q).

Muhim: Google Cloud loyihasi «Production» holatida bo'lishi shart. «Testing»da refresh token 7 kunda o'ladi.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from apps.core.settings_store import get_secret, get_setting

from .base import (AccountInfo, AccountStats, Capability, CommentData, ContentRejectedError, Credentials,
                   DryRunReport, HealthResult, LimitProfile, MediaType, NotFoundError, Page, PlatformError,
                   Platform, PostData, PostMetrics, PublishRequest, PublishResult, RuleProblem, TokenExpiredError, TransientError, AuthError)
from .http import request

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/youtube.upload"]
API = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Kvota narxlari (birlik). Google o'zgartirsa Sozlamalardan yangilanadi.
QUOTA_COST = {"list": 1, "search": 100, "videos.insert": 1600, "thumbnails.set": 50, "comments.insert": 50}


def authorize_url(redirect_uri: str, state: str) -> str:
    q = {"client_id": get_setting("google.client_id", ""), "redirect_uri": redirect_uri, "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
         "include_granted_scopes": "true", "state": state}
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(q)


def exchange_code(code: str, redirect_uri: str) -> Credentials:
    r = requests.post(TOKEN_URL, data={"code": code, "client_id": get_setting("google.client_id", ""),
                                       "client_secret": get_secret("google.client_secret"),
                                       "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, timeout=30)
    if r.status_code >= 400:
        raise AuthError(r.text[:300])
    j = r.json()
    if "refresh_token" not in j:
        raise AuthError("refresh_token berilmadi", user_message_uz="Google refresh token bermadi. Ruxsatni qayta bering (prompt=consent).")
    return Credentials({"refresh_token": j["refresh_token"], "access_token": j["access_token"]},
                       datetime.now(timezone.utc) + timedelta(seconds=int(j["expires_in"]) - 60),
                       scopes=j.get("scope", "").split())


def record_quota(units: int, what: str) -> None:
    from apps.providers.quota import record_usage
    record_usage("youtube_data_api", units=units, note=what)


class YouTubeConnector:
    platform = Platform.YOUTUBE
    capabilities = {Capability.STATS, Capability.POSTS, Capability.COMMENTS, Capability.PUBLISH,
                    Capability.ANALYTICS, Capability.DIRECT_UPLOAD}
    limits = LimitProfile(min_interval_sec=0.2, jitter_sec=0.2, publish_per_day=6)

    def __init__(self, account):
        self.account = account
        c = account.credentials()
        self.refresh_token = c.get("refresh_token", "")
        self.access_token = c.get("access_token", "")
        exp = c.get("access_expires")
        self.access_expires = datetime.fromisoformat(exp) if exp else None

    # ---- token ----
    def _ensure_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self.access_token and self.access_expires and self.access_expires > now + timedelta(minutes=2):
            return self.access_token
        r = requests.post(TOKEN_URL, data={"client_id": get_setting("google.client_id", ""),
                                           "client_secret": get_secret("google.client_secret"),
                                           "refresh_token": self.refresh_token, "grant_type": "refresh_token"}, timeout=30)
        if r.status_code >= 400:
            if "invalid_grant" in r.text:
                raise TokenExpiredError(r.text[:200], user_message_uz="YouTube ruxsati bekor qilingan yoki muddati o'tgan. Qayta ulang (Google loyihasi Production holatida ekanini tekshiring).")
            raise TransientError(r.text[:200])
        j = r.json()
        self.access_token = j["access_token"]
        self.access_expires = now + timedelta(seconds=int(j["expires_in"]) - 60)
        self.account.merge_credentials(access_token=self.access_token, access_expires=self.access_expires.isoformat())
        return self.access_token

    def refresh_credentials(self) -> Credentials | None:
        self.access_token, self.access_expires = "", None
        self._ensure_token()
        return Credentials({**self.account.credentials()}, self.access_expires)

    def _h(self):
        return {"Authorization": f"Bearer {self._ensure_token()}"}

    def _get(self, path: str, cost_key="list", **params):
        r = request("GET", f"{API}/{path}", key="yt", min_interval=self.limits.min_interval_sec,
                    jitter=self.limits.jitter_sec, headers=self._h(), params=params)
        record_quota(QUOTA_COST[cost_key], f"GET {path}")
        return r.json()

    # ---- ulanish ----
    def connect(self, credentials: Credentials | None = None) -> AccountInfo:
        if credentials:
            self.refresh_token = credentials.data.get("refresh_token", self.refresh_token)
            self.access_token = credentials.data.get("access_token", "")
            self.access_expires = credentials.expires_at
        j = self._get("channels", part="snippet,statistics,contentDetails", mine="true")
        if not j.get("items"):
            raise NotFoundError("kanal yo'q", user_message_uz="Bu Google akkauntda YouTube kanal topilmadi.")
        ch = j["items"][0]
        self._uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
        return AccountInfo(ch["id"], ch["snippet"].get("customUrl"), ch["snippet"]["title"],
                           int(ch["statistics"].get("subscriberCount", 0)), raw=ch)

    def health_check(self) -> HealthResult:
        try:
            info = self.connect()
            return HealthResult(True, f"Ulangan: {info.title}")
        except Exception as e:  # noqa: BLE001
            return HealthResult(False, getattr(e, "user_message_uz", str(e)))

    def fetch_account_stats(self) -> AccountStats:
        j = self._get("channels", part="statistics", mine="true")
        s = j["items"][0]["statistics"]
        extra = {}
        views = int(s.get("viewCount", 0))
        try:
            end = datetime.now(timezone.utc).date()
            a = self._analytics("views,estimatedMinutesWatched,subscribersGained,subscribersLost", end - timedelta(days=1), end - timedelta(days=1))
            row = (a.get("rows") or [[0, 0, 0, 0]])[0]
            extra = {"views_yesterday": row[0], "minutes_watched_yesterday": row[1], "subs_gained_yesterday": row[2], "subs_lost_yesterday": row[3]}
        except PlatformError:
            pass
        return AccountStats(datetime.now(timezone.utc), int(s.get("subscriberCount", 0)), posts_count=int(s.get("videoCount", 0)),
                            views=views, extra={k: float(v) for k, v in extra.items()})

    # ---- videolar ----
    def _uploads_playlist(self) -> str:
        if not getattr(self, "_uploads", None):
            self.connect()
        return self._uploads

    @staticmethod
    def _dur(iso: str) -> float:
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
        h, mi, s = (int(x or 0) for x in m.groups()) if m else (0, 0, 0)
        return h * 3600 + mi * 60 + s

    def fetch_posts(self, since: datetime, cursor: str | None = None) -> Page:
        params = {"part": "contentDetails", "playlistId": self._uploads_playlist(), "maxResults": 50}
        if cursor:
            params["pageToken"] = cursor
        j = self._get("playlistItems", **params)
        ids = [i["contentDetails"]["videoId"] for i in j.get("items", [])]
        if not ids:
            return Page([])
        v = self._get("videos", part="snippet,contentDetails,statistics", id=",".join(ids))
        out, stop = [], False
        for it in v.get("items", []):
            ts = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))
            if ts < since:
                stop = True
                continue
            dur = self._dur(it["contentDetails"]["duration"])
            sn = it["snippet"]
            out.append(PostData(it["id"], MediaType.SHORT if 0 < dur <= 180 else MediaType.VIDEO,
                                sn.get("title", "") + ("\n\n" + sn["description"] if sn.get("description") else ""),
                                f"https://www.youtube.com/watch?v={it['id']}", ts, duration_sec=dur,
                                hashtags=[f"#{t}" for t in sn.get("tags", [])][:30], raw=it))
        return Page(out, None if stop else j.get("nextPageToken"))

    def _analytics(self, metrics: str, start, end, **extra):
        params = {"ids": "channel==MINE", "startDate": str(start), "endDate": str(end), "metrics": metrics, **extra}
        r = request("GET", ANALYTICS, key="yt-an", min_interval=0.3, jitter=0.2, headers=self._h(), params=params)
        return r.json()

    def fetch_post_metrics(self, external_ids: list[str]) -> list[PostMetrics]:
        now = datetime.now(timezone.utc)
        out = []
        for i in range(0, len(external_ids), 50):
            chunk = external_ids[i:i + 50]
            v = self._get("videos", part="statistics", id=",".join(chunk))
            for it in v.get("items", []):
                s = it["statistics"]
                m = dict(external_id=it["id"], taken_at=now, views=int(s.get("viewCount", 0)),
                         likes=int(s.get("likeCount", 0)), comments=int(s.get("commentCount", 0)))
                try:
                    a = self._analytics("estimatedMinutesWatched,averageViewDuration,shares", now.date() - timedelta(days=400), now.date(),
                                        filters=f"video=={it['id']}")
                    row = (a.get("rows") or [[0, 0, 0]])[0]
                    m.update(watch_time_sec=float(row[0]) * 60, avg_view_duration_sec=float(row[1]), shares=int(row[2]))
                except PlatformError:
                    pass
                out.append(PostMetrics(**m))
        return out

    def fetch_comments(self, post_external_id: str, since: datetime | None = None) -> Page:
        j = self._get("commentThreads", part="snippet", videoId=post_external_id, maxResults=50, order="time")
        out = []
        for t in j.get("items", []):
            c = t["snippet"]["topLevelComment"]
            sn = c["snippet"]
            ts = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
            if since and ts < since:
                continue
            out.append(CommentData(c["id"], post_external_id, sn.get("authorDisplayName"), sn.get("textDisplay", ""), ts, sn.get("likeCount", 0)))
        return Page(out)

    def fetch_stories(self):
        return []

    def fetch_story_metrics(self, external_ids):
        return []

    # ---- nashr ----
    def dry_run(self, req: PublishRequest) -> DryRunReport:
        probs = []
        title = (req.options.get("title") or (req.text or "").split("\n")[0])[:100]
        if not title:
            probs.append(RuleProblem("yt.title", "block", "YouTube uchun sarlavha kerak.", "title"))
        if not req.media_paths:
            probs.append(RuleProblem("yt.media", "block", "Video fayl kerak."))
        elif not os.path.exists(req.media_paths[0]):
            probs.append(RuleProblem("yt.media_missing", "block", "Video fayl topilmadi."))
        if req.text and len(req.text) > 5000:
            probs.append(RuleProblem("yt.desc", "block", "Tavsif 5000 belgidan oshmasligi kerak."))
        from apps.providers.quota import youtube_uploads_left
        if youtube_uploads_left() <= 0:
            probs.append(RuleProblem("yt.quota", "block", "Bugungi YouTube yuklash kvotasi tugadi."))
        return DryRunReport(not any(p.severity == "block" for p in probs), probs)

    def publish(self, req: PublishRequest) -> PublishResult:
        path = req.media_paths[0]
        text = req.text or ""
        title = (req.options.get("title") or text.split("\n")[0])[:100]
        body = {"snippet": {"title": title, "description": text[:5000], "tags": req.options.get("tags", []),
                            "categoryId": str(req.options.get("category_id", "22"))},
                "status": {"privacyStatus": req.options.get("privacy", "public"), "selfDeclaredMadeForKids": False}}
        h = {**self._h(), "X-Upload-Content-Type": "video/*", "X-Upload-Content-Length": str(os.path.getsize(path))}
        init = request("POST", "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                       key="yt-up", headers=h, json=body)
        record_quota(QUOTA_COST["videos.insert"], "videos.insert")
        from apps.providers.quota import record_youtube_upload
        record_youtube_upload()
        loc = init.headers["Location"]
        with open(path, "rb") as f:
            up = request("PUT", loc, key="yt-up", timeout=3600, headers={"Authorization": h["Authorization"]}, data=f)
        j = up.json()
        privacy = j.get("status", {}).get("privacyStatus")
        raw = dict(j)
        if j.get("status", {}).get("uploadStatus") == "rejected":
            raise ContentRejectedError(str(j.get("status")), user_message_uz="YouTube videoni rad etdi.")
        if body["status"]["privacyStatus"] == "public" and privacy == "private":
            raw["audit_restricted"] = True  # API audit o'tmagan loyiha: video yopiq holatda qoldi
        thumb = req.options.get("thumbnail")
        if thumb and os.path.exists(thumb):
            try:
                with open(thumb, "rb") as tf:
                    request("POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={j['id']}",
                            key="yt-up", headers=self._h(), data=tf)
                record_quota(QUOTA_COST["thumbnails.set"], "thumbnails.set")
            except PlatformError:
                pass
        return PublishResult(j["id"], f"https://www.youtube.com/watch?v={j['id']}", datetime.now(timezone.utc), raw=raw)

    def delete_published(self, external_id: str) -> None:
        request("DELETE", f"{API}/videos", key="yt", headers=self._h(), params={"id": external_id})
