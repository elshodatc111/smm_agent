"""DataProvider shartnomasi (CONTRACTS §3): boshqalarning ochiq ma'lumoti."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from apps.connections.base import Platform


class DataKind(StrEnum):
    PROFILE = "profile"; POSTS = "posts"; VIDEO_LIST = "video_list"
    COMMENTS = "comments"; TRANSCRIPT = "transcript"


@dataclass(frozen=True)
class Cost:
    unit: str   # quota_units | credits
    amount: float


@dataclass(frozen=True)
class DataRequest:
    platform: Platform
    kind: DataKind
    target: str
    limit: int = 20
    cursor: str | None = None
    max_cost: Cost | None = None
    cache_max_age_sec: int | None = None


@dataclass(frozen=True)
class DataResponse:
    provider: str
    data: Any
    cost: Cost
    from_cache: bool
    fetched_at: datetime


@dataclass
class ProviderStatus:
    ok: bool
    remaining: float | None = None
    unit: str = ""
    message_uz: str = ""


class NoProviderAvailable(Exception):
    def __init__(self, reason: str, retry_at: datetime | None = None):
        super().__init__(reason)
        self.retry_at = retry_at


class DataProvider(Protocol):
    name: str
    supports: dict[Platform, set[DataKind]]

    def estimate_cost(self, platform: Platform, kind: DataKind, count: int) -> Cost: ...
    def fetch(self, req: DataRequest) -> DataResponse: ...
    def status(self) -> ProviderStatus: ...
