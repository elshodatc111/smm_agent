"""Instagram API with Instagram Login (rasmiy). Facebook Page KERAK EMAS.

Login/parol ishlatilmaydi. Token: uzoq muddatli (60 kun), muddatidan oldin yangilanadi.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from apps.core.settings_store import get_secret, get_setting

from .base import (AccountInfo, AccountStats, Capability, CommentData, ContentRejectedError, Credentials,
                   DryRunReport, HealthResult, LimitProfile, MediaType, Page, PlatformError, Platform,
                   PostData, PostMetrics, PublishRequest, PublishResult, RuleProblem, TokenExpiredError,
                   TransientError, UnsupportedOperation, AuthError, RateLimitError)
import logging

log = logging.getLogger(__name__)
from .http import request

GRAPH_VERSION = "v23.0"
GRAPH = f"https://graph.instagram.com/{GRAPH_VERSION}"
SCOPES = ["instagram_business_basic", "instagram_business_content_publish",
          "instagram_business_manage_comments", "instagram_business_manage_insights"]
READ_SCOPES = ["instagram_business_basic", "instagram_business_manage_insights", "instagram_business_manage_comments"]

# media_product_type bo'yicha insights metrikalari (xato bo'lsa kichraytirib qayta uriniladi)
METRICS = {
    "REELS": ["views", "reach", "saved", "shares", "likes", "comments", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"],
    "FEED": ["views", "reach", "saved", "shares", "likes", "comments"],
    "STORY": ["views", "reach", "replies", "shares", "total_interactions", "follows", "profile_visits"],
}


def _unreadable(e: Exception) -> bool:
    """Meta: «Object with ID ... does not exist, cannot be loaded due to missing permissions» — bitta postni o'qib bo'lmaydi."""
    m = str(e).lower()
    return any(k in m for k in ("does not exist", "unsupported get request", "missing permissions", "cannot be loaded", "has been deleted"))


def authorize_url(redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
    q = {"client_id": get_setting("meta.app_id", ""), "redirect_uri": redirect_uri, "response_type": "code",
         "scope": ",".join(scopes or SCOPES), "state": state, "enable_fb_login": "0", "force_authentication": "1", "force_reauth": "true"}
    return "https://www.instagram.com/oauth/authorize?" + urlencode(q)


def exchange_code(code: str, redirect_uri: str) -> Credentials:
    """code -> qisqa token -> uzoq muddatli token (60 kun)."""
    r = request("POST", "https://api.instagram.com/oauth/access_token", key="ig_oauth",
                data={"client_id": get_setting("meta.app_id", ""), "client_secret": get_secret("meta.app_secret"),
                      "grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code})
    short = r.json()
    r2 = request("GET", "https://graph.instagram.com/access_token", key="ig_oauth",
                 params={"grant_type": "ig_exchange_token", "client_secret": get_secret("meta.app_secret"),
                         "access_token": short["access_token"]})
    j = r2.json()
    return Credentials({"access_token": j["access_token"], "ig_user_id": str(short.get("user_id", ""))},
                       datetime.now(timezone.utc) + timedelta(seconds=int(j.get("expires_in", 5184000))),
                       scopes=short.get("permissions") if isinstance(short.get("permissions"), list) else SCOPES)


class InstagramConnector:
    platform = Platform.INSTAGRAM
    capabilities = {Capability.STATS, Capability.POSTS, Capability.COMMENTS, Capability.STORIES,
                    Capability.PUBLISH, Capability.ANALYTICS, Capability.DIRECT_UPLOAD}
    limits = LimitProfile(min_interval_sec=0.6, jitter_sec=0.6, publish_per_day=50)

    def __init__(self, account):
        self.account = account
        c = account.credentials()
        self.token = c.get("access_token", "")
        self.ig_id = c.get("ig_user_id") or account.external_id or "me"

    # ---- yordamchi ----
    def _get(self, path: str, **params):
        params["access_token"] = self.token
        try:
            r = request("GET", f"{GRAPH}/{path}", key=f"ig:{self.ig_id}", min_interval=self.limits.min_interval_sec,
                        jitter=self.limits.jitter_sec, params=params)
        except AuthError as e:
            raise TokenExpiredError(str(e)) from e
        return r.json()

    def _post(self, path: str, **data):
        data["access_token"] = self.token
        try:
            r = request("POST", f"{GRAPH}/{path}", key=f"ig:{self.ig_id}", min_interval=self.limits.min_interval_sec,
                        jitter=self.limits.jitter_sec, data=data)
        except AuthError as e:
            raise TokenExpiredError(str(e)) from e
        return r.json()

    # ---- ulanish ----
    def connect(self, credentials: Credentials | None = None) -> AccountInfo:
        if credentials:
            self.token = credentials.data["access_token"]
        j = self._get("me", fields="user_id,username,name,account_type,profile_picture_url,followers_count,follows_count,media_count")
        self.ig_id = str(j.get("user_id") or j.get("id"))
        if j.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR", "CREATOR"):
            raise PlatformError("professional emas", user_message_uz="Instagram akkaunt Professional (Business/Creator) bo'lishi kerak.")
        return AccountInfo(self.ig_id, j.get("username"), j.get("name") or j.get("username", ""),
                           j.get("followers_count"), j.get("profile_picture_url"), raw=j)

    def health_check(self) -> HealthResult:
        try:
            info = self.connect()
            exp = self.account.token_expires_at
            return HealthResult(True, f"Ulangan: @{info.handle}", exp)
        except Exception as e:  # noqa: BLE001
            return HealthResult(False, getattr(e, "user_message_uz", str(e)))

    def refresh_credentials(self) -> Credentials | None:
        j = request("GET", "https://graph.instagram.com/refresh_access_token", key="ig_oauth",
                    params={"grant_type": "ig_refresh_token", "access_token": self.token}).json()
        self.token = j["access_token"]
        return Credentials({**self.account.credentials(), "access_token": j["access_token"]},
                           datetime.now(timezone.utc) + timedelta(seconds=int(j.get("expires_in", 5184000))))

    # ---- o'qish ----
    def fetch_account_stats(self) -> AccountStats:
        j = self._get("me", fields="followers_count,follows_count,media_count")
        extra, reach, views, visits = {}, None, None, None
        try:
            ins = self._get(f"{self.ig_id}/insights", metric="reach,views,profile_views,accounts_engaged",
                            period="day", metric_type="total_value")
            vals = {d["name"]: d.get("total_value", {}).get("value") for d in ins.get("data", [])}
            reach, views, visits = vals.get("reach"), vals.get("views"), vals.get("profile_views")
            if vals.get("accounts_engaged") is not None:
                extra["accounts_engaged"] = float(vals["accounts_engaged"])
        except PlatformError:
            pass  # insights ba'zan 100 obunachidan kam akkauntlarda yo'q
        return AccountStats(datetime.now(timezone.utc), j.get("followers_count"), j.get("follows_count"),
                            j.get("media_count"), reach=reach, views=views, profile_visits=visits, extra=extra)

    @staticmethod
    def _mtype(m: dict) -> MediaType:
        pt, mt = m.get("media_product_type"), m.get("media_type")
        if pt == "REELS":
            return MediaType.REEL
        if pt == "STORY":
            return MediaType.STORY
        return {"VIDEO": MediaType.VIDEO, "CAROUSEL_ALBUM": MediaType.CAROUSEL}.get(mt, MediaType.IMAGE)

    def fetch_posts(self, since: datetime, cursor: str | None = None) -> Page:
        params = {"fields": "id,caption,media_type,media_product_type,permalink,timestamp,media_url,thumbnail_url,like_count,comments_count",
                  "limit": 50}
        if cursor:
            params["after"] = cursor
        j = self._get(f"{self.ig_id}/media", **params)
        out = []
        for m in j.get("data", []):
            ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00").replace("+0000", "+00:00"))
            if ts < since:
                return Page(out, None)
            cap = m.get("caption") or ""
            out.append(PostData(m["id"], self._mtype(m), cap, m.get("permalink"), ts,
                                [u for u in (m.get("media_url"),) if u],
                                hashtags=[w for w in cap.split() if w.startswith("#")], raw=m))
        return Page(out, j.get("paging", {}).get("cursors", {}).get("after") if j.get("paging", {}).get("next") else None)

    def _insights(self, media_id: str, kind: str) -> dict:
        metrics = list(METRICS[kind])
        while metrics:
            try:
                j = self._get(f"{media_id}/insights", metric=",".join(metrics))
                return {d["name"]: (d["values"][0]["value"] if d.get("values") else None) for d in j.get("data", [])}
            except PlatformError as e:
                msg = str(e).lower()
                if "does not support" in msg or "metric" in msg:
                    metrics = metrics[:-1]  # qo'llanmaydigan metrikani tashlab qayta urinish
                    continue
                raise
        return {}

    def fetch_post_metrics(self, external_ids: list[str]) -> list[PostMetrics]:
        now = datetime.now(timezone.utc)
        out = []
        for mid in external_ids:
            try:
                base = self._get(mid, fields="like_count,comments_count,media_product_type")
                kind = "REELS" if base.get("media_product_type") == "REELS" else "FEED"
                ins = self._insights(mid, kind)
            except (AuthError, RateLimitError):
                raise   # token/limit muammosi — butun yig'ish to'xtashi kerak
            except PlatformError as e:
                if _unreadable(e):   # post o'chirilgan yoki ruxsat yo'q — qolgan postlar yig'ilaversin
                    log.info("Instagram post %s metrikasi o'qilmadi (o'tkazib yuborildi): %s", mid, str(e)[:160])
                    continue
                raise
            out.append(PostMetrics(mid, now, views=ins.get("views"), likes=base.get("like_count", ins.get("likes")),
                                   comments=base.get("comments_count", ins.get("comments")), shares=ins.get("shares"),
                                   saves=ins.get("saved"), reach=ins.get("reach"),
                                   watch_time_sec=(ins.get("ig_reels_video_view_total_time") or 0) / 1000 or None,
                                   avg_view_duration_sec=(ins.get("ig_reels_avg_watch_time") or 0) / 1000 or None))
        return out

    def fetch_comments(self, post_external_id: str, since: datetime | None = None) -> Page:
        j = self._get(f"{post_external_id}/comments", fields="id,text,username,timestamp,like_count", limit=50)
        out = []
        for c in j.get("data", []):
            ts = datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00").replace("+0000", "+00:00"))
            if since and ts < since:
                continue
            out.append(CommentData(c["id"], post_external_id, c.get("username"), c.get("text", ""), ts, c.get("like_count", 0)))
        return Page(out)

    def fetch_stories(self) -> list[PostData]:
        j = self._get(f"{self.ig_id}/stories", fields="id,media_type,media_url,permalink,timestamp,caption")
        return [PostData(m["id"], MediaType.STORY, m.get("caption"), m.get("permalink"),
                         datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")), raw=m) for m in j.get("data", [])]

    def _story_navigation(self, sid: str) -> dict:
        """Chuqur yig'ish: oldinga/orqaga bosish, keyingisiga o'tish, chiqib ketish (breakdown)."""
        try:
            j = self._get(f"{sid}/insights", metric="navigation", breakdown="story_navigation_action_type")
            out = {}
            for d in j.get("data", []):
                for b in ((d.get("total_value") or {}).get("breakdowns") or []):
                    for r in b.get("results", []):
                        k = (r.get("dimension_values") or ["?"])[0]
                        out[f"nav_{k}"] = float(r.get("value") or 0)
            return out
        except (AuthError, RateLimitError):
            raise
        except PlatformError:
            return {}

    def fetch_story_metrics(self, external_ids: list[str], deep: bool = False) -> list[PostMetrics]:
        now = datetime.now(timezone.utc)
        out = []
        for sid in external_ids:
            try:
                ins = self._insights(sid, "STORY")
            except (AuthError, RateLimitError):
                raise
            except PlatformError as e:
                if _unreadable(e):   # story muddati tugagan bo'lishi mumkin
                    continue
                raise
            extra = {k: float(v) for k, v in ins.items() if v is not None}
            if deep:
                extra.update(self._story_navigation(sid))
                extra["deep"] = 1.0
            out.append(PostMetrics(sid, now, views=ins.get("views"), reach=ins.get("reach"), shares=ins.get("shares"),
                                   comments=ins.get("replies"), extra=extra))
        return out

    # ---- nashr ----
    def publish_quota(self) -> dict:
        j = self._get(f"{self.ig_id}/content_publishing_limit", fields="quota_usage,config")
        d = (j.get("data") or [{}])[0]
        return {"used": d.get("quota_usage", 0), "total": (d.get("config") or {}).get("quota_total", 100)}

    def dry_run(self, req: PublishRequest) -> DryRunReport:
        probs = []
        if req.text and len(req.text) > 2200:
            probs.append(RuleProblem("ig.caption", "block", "Instagram izohi 2200 belgidan oshmasligi kerak.", "text"))
        if req.media_type != MediaType.TEXT and not req.media_paths and not req.media_public_urls:
            probs.append(RuleProblem("ig.media", "block", "Instagram uchun rasm yoki video kerak."))
        if req.media_type == MediaType.TEXT:
            probs.append(RuleProblem("ig.text_only", "block", "Instagram faqat matnli post qabul qilmaydi."))
        try:
            q = self.publish_quota()
            if q["used"] >= q["total"]:
                probs.append(RuleProblem("ig.quota", "block", "Instagram 24 soatlik nashr limitiga yetdi."))
        except PlatformError:
            pass
        return DryRunReport(not any(p.severity == "block" for p in probs), probs)

    def _wait_container(self, cid: str, timeout: int) -> None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            st = self._get(cid, fields="status_code,status").get("status_code")
            if st == "FINISHED":
                return
            if st in ("ERROR", "EXPIRED"):
                raise ContentRejectedError(str(st), user_message_uz="Instagram faylni qabul qilmadi (format/davomiylik).")
            time.sleep(3)
        raise TransientError("container tayyor bo'lmadi")

    def _resumable_upload(self, container: dict, path: str) -> None:
        uri = container["uri"]
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            request("POST", uri, key=f"ig-upload:{self.ig_id}", timeout=600,
                    headers={"Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(size)}, data=f)

    def publish(self, req: PublishRequest) -> PublishResult:
        mt = req.media_type
        params: dict = {}
        is_video = mt in (MediaType.REEL, MediaType.VIDEO, MediaType.SHORT) or (
            mt == MediaType.STORY and req.media_paths and req.media_paths[0].lower().endswith((".mp4", ".mov", ".m4v")))
        if not is_video and mt not in (MediaType.CAROUSEL, MediaType.STORY) and req.media_paths and req.media_paths[0].lower().endswith((".mp4", ".mov", ".m4v")):
            is_video = True   # «Rasm» turi tanlangan, lekin fayl video — Reels sifatida yuboriladi
        caption = req.text or ""
        use_upload = is_video and mt != MediaType.STORY and req.media_paths and req.options.get("upload_mode", "resumable") == "resumable"   # Stories uchun resumable ishlamaydi: video_url kerak
        if mt == MediaType.CAROUSEL:
            if not 2 <= len(req.media_public_urls) <= 10:
                raise ContentRejectedError("carousel soni", user_message_uz=f"Karuselda 2–10 ta rasm/video bo'lishi kerak (hozir {len(req.media_public_urls)} ta). Postga yana fayl qo'shing va qayta urinib ko'ring.")
            kids = []
            for i, u in enumerate(req.media_public_urls):
                src = (req.media_paths[i] if i < len(req.media_paths) else u).lower().split("?")[0]   # kengaytma asl fayldan (vaqtinchalik havolada bo'lmasligi mumkin)
                if src.endswith((".mp4", ".mov", ".m4v")):
                    extra = {"media_type": "VIDEO", "video_url": u}
                else:
                    extra = {"image_url": u}
                kids.append(self._post(f"{self.ig_id}/media", is_carousel_item="true", **extra)["id"])
            for k in kids:
                self._wait_container(k, 300)
            params = {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption}
        elif mt == MediaType.STORY:
            params = {"media_type": "STORIES"}
        elif is_video:
            params = {"media_type": "REELS", "caption": caption, "share_to_feed": "true"}
        else:
            params = {"caption": caption}
        if mt != MediaType.CAROUSEL:
            if use_upload:
                params["upload_type"] = "resumable"
            elif req.media_public_urls:
                params["video_url" if is_video else "image_url"] = req.media_public_urls[0]
            else:
                raise ContentRejectedError("ochiq URL yo'q", user_message_uz="Rasm uchun vaqtinchalik ochiq havola (Worker/R2) kerak.")
        c = self._post(f"{self.ig_id}/media", **params)
        if use_upload:
            self._resumable_upload(c, req.media_paths[0])
        self._wait_container(c["id"], 600 if is_video else 120)
        pub = self._post(f"{self.ig_id}/media_publish", creation_id=c["id"])
        info = self._get(pub["id"], fields="permalink,timestamp")
        return PublishResult(pub["id"], info.get("permalink"), datetime.now(timezone.utc), raw=pub)

    def delete_published(self, external_id: str) -> None:
        raise UnsupportedOperation("Instagram API orqali post o'chirib bo'lmaydi.")
