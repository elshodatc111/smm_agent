from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from apps.core.compat import StrEnum
from typing import Protocol


class TaskType(StrEnum):
    LONG_UZ = "long_uz"; CLASSIFY = "classify"; VISION = "vision"; STT = "stt"
    BRAND_PROFILE = "brand_profile"; SCRIPT_REVIEW = "script_review"; COMMENT_REPLY = "comment_reply"
    WHY_WORKED = "why_worked"; AD_PLAN = "ad_plan"


COMPLEX_TASKS = {TaskType.LONG_UZ, TaskType.SCRIPT_REVIEW, TaskType.AD_PLAN, TaskType.BRAND_PROFILE}


@dataclass(frozen=True)
class Attachment:
    mime: str
    data: bytes
    name: str = "file"


@dataclass(frozen=True)
class AIRequest:
    task: TaskType
    prompt: str
    business_id: int | None = None
    system_extra: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    response_schema: dict | None = None
    priority: int = 5
    cache_ttl_sec: int | None = None
    require_lang: str | None = "uz"
    kind: str = ""
    options: dict = field(default_factory=dict)  # stt: language, prompt


@dataclass(frozen=True)
class LangCheck:
    ok: bool
    score: float
    reason: str = ""


@dataclass
class RawAIResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AIResult:
    text: str | None
    data: dict | None
    provider: str
    model: str
    key_alias: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    from_cache: bool
    lang_check: LangCheck | None = None
    extra: dict = field(default_factory=dict)


class AIProvider(Protocol):
    name: str
    def supports(self, task: TaskType) -> bool: ...
    def call(self, req: AIRequest, key: str, model: str, system: str) -> RawAIResponse: ...
