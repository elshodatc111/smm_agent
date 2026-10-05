"""Connector shartnomasi (CONTRACTS §1-2): DTO, xatolar, interfeys."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class Platform(StrEnum):
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"


class MediaType(StrEnum):
    TEXT = "text"; IMAGE = "image"; VIDEO = "video"; ALBUM = "album"
    REEL = "reel"; SHORT = "short"; STORY = "story"; CAROUSEL = "carousel"


class Capability(StrEnum):
    STATS = "stats"; POSTS = "posts"; COMMENTS = "comments"; STORIES = "stories"
    PUBLISH = "publish"; ANALYTICS = "analytics"; DIRECT_UPLOAD = "direct_upload"


# ---------- xatolar ----------
class PlatformError(Exception):
    code = "platform_error"
    retryable = False
    user_message_uz = "Tarmoq xatosi."

    def __init__(self, message: str = "", *, user_message_uz: str | None = None, retry_after: int | None = None):
        super().__init__(message or self.user_message_uz)
        if user_message_uz:
            self.user_message_uz = user_message_uz
        self.retry_after = retry_after


class AuthError(PlatformError):
    code = "auth"; user_message_uz = "Ulanishda avtorizatsiya xatosi. Qayta ulang."


class TokenExpiredError(AuthError):
    code = "token_expired"; user_message_uz = "Ulanish muddati tugagan, qayta ulang."


class PermissionMissingError(PlatformError):
    code = "permission"; user_message_uz = "Ruxsat yetarli emas."


class RateLimitError(PlatformError):
    code = "rate_limit"; retryable = True; user_message_uz = "So'rovlar limiti. Birozdan keyin qayta urinadi."


class QuotaExceededError(PlatformError):
    code = "quota"; retryable = True; user_message_uz = "Kunlik limit tugadi."


class NotFoundError(PlatformError):
    code = "not_found"; user_message_uz = "Topilmadi."


class TransientError(PlatformError):
    code = "transient"; retryable = True; user_message_uz = "Vaqtinchalik xato. Qayta urinadi."


class ContentRejectedError(PlatformError):
    code = "rejected"; user_message_uz = "Platforma kontentni qabul qilmadi."


class UnsupportedOperation(PlatformError):
    code = "unsupported"; user_message_uz = "Bu amal ushbu tarmoqda qo'llab-quvvatlanmaydi."


# ---------- DTO ----------
@dataclass(frozen=True)
class AccountInfo:
    external_id: str
    handle: str | None
    title: str
    followers: int | None
    avatar_url: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AccountStats:
    taken_at: datetime
    followers: int | None
    following: int | None = None
    posts_count: int | None = None
    reach: int | None = None
    impressions: int | None = None
    views: int | None = None
    profile_visits: int | None = None
    extra: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PostData:
    external_id: str
    media_type: MediaType
    text: str | None
    url: str | None
    published_at: datetime
    media_urls: list[str] = field(default_factory=list)
    duration_sec: float | None = None
    hashtags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PostMetrics:
    external_id: str
    taken_at: datetime
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    saves: int | None = None
    reach: int | None = None
    reactions: dict[str, int] = field(default_factory=dict)
    watch_time_sec: float | None = None
    avg_view_duration_sec: float | None = None
    ctr: float | None = None
    extra: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CommentData:
    external_id: str
    post_external_id: str
    author_name: str | None
    text: str
    created_at: datetime
    like_count: int = 0
    parent_external_id: str | None = None


@dataclass(frozen=True)
class Page:
    items: list[Any]
    next_cursor: str | None = None


@dataclass(frozen=True)
class RuleProblem:
    rule_id: str
    severity: str  # pass|warn|block
    message_uz: str
    field: str | None = None
    suggestion_uz: str | None = None


@dataclass(frozen=True)
class DryRunReport:
    ok: bool
    problems: list[RuleProblem] = field(default_factory=list)


@dataclass(frozen=True)
class PublishRequest:
    idempotency_key: str
    media_type: MediaType
    text: str | None
    media_paths: list[str]
    scheduled_at: datetime | None = None
    options: dict[str, Any] = field(default_factory=dict)
    media_public_urls: list[str] = field(default_factory=list)  # R2 zaxira yo'li uchun


@dataclass(frozen=True)
class PublishResult:
    external_id: str
    url: str | None
    published_at: datetime
    raw: dict = field(default_factory=dict)


@dataclass
class Credentials:
    data: dict[str, Any]
    expires_at: datetime | None = None
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    message_uz: str = ""
    token_expires_at: datetime | None = None
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LimitProfile:
    min_interval_sec: float = 0.3
    jitter_sec: float = 0.2
    publish_per_day: int | None = None


class Connector(Protocol):
    platform: Platform
    capabilities: set[Capability]
    limits: LimitProfile

    def connect(self, credentials: Credentials) -> AccountInfo: ...
    def health_check(self) -> HealthResult: ...
    def fetch_account_stats(self) -> AccountStats: ...
    def fetch_posts(self, since: datetime, cursor: str | None = None) -> Page: ...
    def fetch_post_metrics(self, external_ids: list[str]) -> list[PostMetrics]: ...
    def fetch_comments(self, post_external_id: str, since: datetime | None = None) -> Page: ...
    def fetch_stories(self) -> list[PostData]: ...
    def fetch_story_metrics(self, external_ids: list[str]) -> list[PostMetrics]: ...
    def refresh_credentials(self) -> Credentials | None: ...
    def dry_run(self, req: PublishRequest) -> DryRunReport: ...
    def publish(self, req: PublishRequest) -> PublishResult: ...
    def delete_published(self, external_id: str) -> None: ...
