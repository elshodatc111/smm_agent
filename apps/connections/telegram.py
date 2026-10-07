"""Telegram kanal connector: Bot API (nashr, soni) + ochiq sahifa / Telethon (statistika)."""
from __future__ import annotations

import json
from datetime import datetime, timezone


from .base import (AccountInfo, AccountStats, AuthError, Capability, Credentials, DryRunReport,
                   HealthResult, LimitProfile, MediaType, Page, PermissionMissingError, Platform, PostMetrics, PublishRequest, PublishResult, RuleProblem)
from .http import request
from apps.content import richtext
from .public_tme import PublicChannelScraper

API = "https://api.telegram.org"


class TelegramChannelConnector:
    platform = Platform.TELEGRAM
    capabilities = {Capability.STATS, Capability.POSTS, Capability.PUBLISH, Capability.DIRECT_UPLOAD}
    limits = LimitProfile(min_interval_sec=0.05, jitter_sec=0.05)

    def __init__(self, account):
        self.account = account
        self.chat = account.credentials().get("chat") or account.handle or account.external_id
        self.bot = account.bot
        self._tg = None
        if account.tg_session_id:
            self.capabilities = self.capabilities | {Capability.ANALYTICS}

    # --- Bot API ---
    def _call(self, method: str, **params):
        token = self.bot.token() if self.bot else self.account.credentials().get("bot_token", "")
        files = params.pop("_files", None)
        timeout = 30
        if files:   # yuklash vaqti fayl hajmiga qarab: ~0,3 MB/s deb hisoblab, kamida 2 daqiqa
            import os
            mb = sum(os.path.getsize(f.name) for f in files.values() if getattr(f, "name", None) and os.path.exists(f.name)) / 1e6
            timeout = (15, int(min(900, max(120, mb * 4))))
        resp = request("POST", f"{API}/bot{token}/{method}", key=f"tgbot:{token[:8]}",
                       min_interval=self.limits.min_interval_sec, jitter=self.limits.jitter_sec,
                       data=params if files else None, json=None if files else params, files=files, timeout=timeout)
        j = resp.json()
        if not j.get("ok"):
            raise AuthError(str(j.get("description")))
        return j["result"]

    def connect(self, credentials: Credentials | None = None) -> AccountInfo:
        chat = self._call("getChat", chat_id=self.chat)
        self._check_admin(chat["id"])
        n = self._call("getChatMemberCount", chat_id=chat["id"])
        return AccountInfo(str(chat["id"]), chat.get("username"), chat.get("title", ""), n, raw=chat)

    def _check_admin(self, chat_id) -> None:
        me = self._call("getMe")
        m = self._call("getChatMember", chat_id=chat_id, user_id=me["id"])
        missing = []
        if m.get("status") != "administrator":
            raise PermissionMissingError("bot admin emas",
                                         user_message_uz="Bot kanalda to'liq admin emas: kanalga botni administrator qilib qo'shing.")
        for perm, label in (("can_post_messages", "post yuborish"), ("can_edit_messages", "tahrirlash"),
                            ("can_delete_messages", "o'chirish")):
            if not m.get(perm):
                missing.append(label)
        if missing:
            raise PermissionMissingError("ruxsat yetarli emas: " + ",".join(missing),
                                         user_message_uz="Botga quyidagi ruxsatlar yetishmaydi: " + ", ".join(missing))

    def health_check(self) -> HealthResult:
        try:
            info = self.connect()
            return HealthResult(True, f"Ulangan: {info.title}, {info.followers} obunachi")
        except Exception as e:  # noqa: BLE001
            return HealthResult(False, getattr(e, "user_message_uz", str(e)))

    def fetch_account_stats(self) -> AccountStats:
        n = self._call("getChatMemberCount", chat_id=self.chat)
        return AccountStats(datetime.now(timezone.utc), n)

    def _public(self):
        h = self.account.handle
        return PublicChannelScraper(h) if h else None

    def fetch_posts(self, since: datetime, cursor: str | None = None) -> Page:
        pub = self._public()
        if pub:
            return pub.fetch_posts(since, cursor)
        return Page([])

    def fetch_post_metrics(self, external_ids: list[str]) -> list[PostMetrics]:
        pub = self._public()
        if not pub:
            return []
        page = pub.fetch_posts(datetime(2000, 1, 1, tzinfo=timezone.utc), None)
        want = set(external_ids)
        return pub.fetch_post_metrics([p for p in page.items if p.external_id in want])

    def fetch_comments(self, post_external_id, since=None) -> Page:
        return Page([])

    def fetch_stories(self):
        return []

    def fetch_story_metrics(self, external_ids):
        return []

    def refresh_credentials(self):
        return None

    # --- nashr ---
    def dry_run(self, req: PublishRequest) -> DryRunReport:
        probs = []
        limit = 1024 if req.media_paths else 4096
        if req.text and richtext.visible_len(req.text) > limit:
            probs.append(RuleProblem("tg.text_length", "block", f"Matn {limit} belgidan oshmasligi kerak (teglar hisobga olinmaydi).", "text"))
        if not req.text and not req.media_paths:
            probs.append(RuleProblem("tg.empty", "block", "Matn yoki media kerak."))
        try:
            self._check_admin(self._call("getChat", chat_id=self.chat)["id"])
        except Exception as e:  # noqa: BLE001
            probs.append(RuleProblem("tg.permission", "block", getattr(e, "user_message_uz", str(e))))
        return DryRunReport(not any(p.severity == "block" for p in probs), probs)

    def publish(self, req: PublishRequest) -> PublishResult:
        extra = {"parse_mode": req.options.get("parse_mode", "HTML")}
        text = richtext.sanitize_tg(req.text) if extra["parse_mode"] == "HTML" else (req.text or "")
        markup = req.options.get("buttons")
        if markup:
            extra["reply_markup"] = json.dumps({"inline_keyboard": markup})
        paths = req.media_paths
        if not paths:
            r = self._call("sendMessage", chat_id=self.chat, text=text, **extra)
        elif len(paths) == 1:
            kind = "sendVideo" if req.media_type in (MediaType.VIDEO, MediaType.REEL, MediaType.SHORT) else "sendPhoto"
            field = "video" if kind == "sendVideo" else "photo"
            with open(paths[0], "rb") as f:
                r = self._call(kind, chat_id=self.chat, caption=text, _files={field: f}, **extra)
        else:
            media, files = [], {}
            for i, p in enumerate(paths[:10]):
                is_vid = p.lower().endswith((".mp4", ".mov"))
                media.append({"type": "video" if is_vid else "photo", "media": f"attach://f{i}",
                              **({"caption": text, "parse_mode": extra["parse_mode"]} if i == 0 else {})})
                files[f"f{i}"] = open(p, "rb")
            try:
                r = self._call("sendMediaGroup", chat_id=self.chat, media=json.dumps(media), _files=files)
            finally:
                for f in files.values():
                    f.close()
            r = r[0]
        mid = r["message_id"]
        un = (r.get("chat") or {}).get("username") or self.account.handle
        return PublishResult(f"{r['chat']['id']}/{mid}", f"https://t.me/{un}/{mid}" if un else None,
                             datetime.fromtimestamp(r["date"], timezone.utc), raw=r)

    def delete_published(self, external_id: str) -> None:
        chat, mid = external_id.rsplit("/", 1)
        self._call("deleteMessage", chat_id=chat, message_id=int(mid))
