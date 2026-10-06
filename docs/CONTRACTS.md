# CONTRACTS.md — SMM Platforma shartnomalari (v0.1, qoralama)

Bu hujjat modullar orasidagi **o'zgarmas kelishuvlar**: interfeyslar, ma'lumot shakllari, kodlar, holatlar. Kod shunga moslanadi, aksincha emas. O'zgartirish faqat foydalanuvchi roziligi bilan va `DECISIONS.md`ga yozilgan holda.

Belgilar: `Python` kod bloklari — imzo (interfeys). Identifikatorlar inglizcha, foydalanuvchi matnlari o'zbekcha.

---

## 1. Umumiy tiplar

```python
from dataclasses import dataclass, field
from datetime import datetime          # har doim tz-aware (UTC)
from enum import StrEnum
from typing import Any, Protocol

class Platform(StrEnum):
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"

class MediaType(StrEnum):
    TEXT = "text"; IMAGE = "image"; VIDEO = "video"; ALBUM = "album"
    REEL = "reel"; SHORT = "short"; STORY = "story"; CAROUSEL = "carousel"

class ConnectionStatus(StrEnum):
    ACTIVE = "active"; PAUSED = "paused"; ERROR = "error"
    TOKEN_EXPIRING = "token_expiring"; ARCHIVED = "archived"

@dataclass(frozen=True)
class Page:               # sahifalash uchun
    items: list[Any]
    next_cursor: str | None = None
```

**Umumiy qoidalar**
- Vaqt: tz-aware UTC `datetime`. Pul: `Decimal`, valyuta `UZS`/`USD` alohida maydonda.
- Barcha connector/provayder metodlari xatoda faqat §2.2 dagi `PlatformError` ierarxiyasidan istisno ko'taradi.
- Tashqaridan kelgan xom javob `raw: dict` sifatida DTO ichida saqlanadi (debug uchun), lekin biznes mantig'i `raw`ga tayanmaydi.

---

## 2. Connector shartnomasi (tarmoq)

### 2.1. DTO'lar

```python
@dataclass(frozen=True)
class AccountInfo:
    external_id: str
    handle: str | None
    title: str
    followers: int | None
    avatar_url: str | None = None
    raw: dict = field(default_factory=dict)

@dataclass(frozen=True)
class AccountStats:            # bitta o'lchov nuqtasi
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
    reactions: dict[str, int] = field(default_factory=dict)   # telegram
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
class PublishRequest:
    idempotency_key: str            # content_item_id + platform + attempt_group
    media_type: MediaType
    text: str | None
    media_paths: list[str]          # lokal fayllar
    scheduled_at: datetime | None
    options: dict[str, Any]         # YouTube: title, tags, privacy; IG: location, alt-text; TG: buttons, parse_mode

@dataclass(frozen=True)
class PublishResult:
    external_id: str
    url: str | None
    published_at: datetime
    raw: dict = field(default_factory=dict)

@dataclass(frozen=True)
class DryRunReport:
    ok: bool
    problems: list["RuleProblem"]    # §8.3
```

### 2.2. Xatolar

```python
class PlatformError(Exception):
    code: str
    retryable: bool
    user_message_uz: str           # UI uchun tushunarli matn
class AuthError(PlatformError): ...          # code="auth"       retryable=False  → ulanish ERROR
class TokenExpiredError(AuthError): ...      # code="token_expired"
class PermissionMissingError(PlatformError): ...   # code="permission"  (masalan, bot admin emas)
class RateLimitError(PlatformError): ...     # code="rate_limit" retryable=True, retry_after: int|None
class QuotaExceededError(PlatformError): ... # code="quota"      retryable=True (keyingi oynada)
class NotFoundError(PlatformError): ...      # code="not_found"  retryable=False
class TransientError(PlatformError): ...     # code="transient"  retryable=True (5xx, timeout, tarmoq)
class ContentRejectedError(PlatformError): ...# code="rejected"   retryable=False (format/siyosat)
```

### 2.3. Interfeys

```python
class Connector(Protocol):
    platform: Platform

    def connect(self, credentials: "Credentials") -> AccountInfo: ...
    def health_check(self) -> "HealthResult": ...                 # token + ruxsatlar + oxirgi muvaffaqiyat
    def fetch_account_stats(self) -> AccountStats: ...
    def fetch_posts(self, since: datetime, cursor: str | None = None) -> Page: ...      # Page[PostData]
    def fetch_post_metrics(self, external_ids: list[str]) -> list[PostMetrics]: ...
    def fetch_comments(self, post_external_id: str, since: datetime | None = None) -> Page: ...
    def fetch_stories(self) -> list[PostData]: ...                # faqat hozir faol storilar
    def fetch_story_metrics(self, external_ids: list[str]) -> list[PostMetrics]: ...
    def refresh_credentials(self) -> "Credentials | None": ...    # token yangilash (kerak bo'lsa)
    def dry_run(self, req: PublishRequest) -> DryRunReport: ...
    def publish(self, req: PublishRequest) -> PublishResult: ...  # idempotent: bir xil key → bir xil natija
    def delete_published(self, external_id: str) -> None: ...     # faqat xato tozalash uchun, UI'da yo'q
```

Majburiy xossalar:
- Hamma metodlar `RateLimiter`dan o'tadi (har connector o'z limit profilini e'lon qiladi: `limits: LimitProfile`).
- Qo'llab-quvvatlanmaydigan metod `NotImplementedError` emas, `UnsupportedOperation` (capability bayrog'i bilan oldindan aytiladi): `capabilities: set[Capability]` (`STATS`, `POSTS`, `COMMENTS`, `STORIES`, `PUBLISH`, `ANALYTICS`).
- `publish` ikki marta bir xil `idempotency_key` bilan chaqirilsa, ikkinchi nashr yaratmaydi (avval `publish_attempts` jadvali tekshiriladi, tashqi tarmoqda ham mavjudlik tekshiruvi qilinadi).

### 2.4. Platformaga xos kelishuvlar

**Telegram (`TelegramChannelConnector`)** — Bot API + (ixtiyoriy) `TelethonReadOnlyClient`.
- `connect`: `getChat`, `getChatMember(bot)` → `can_post_messages`, `can_edit_messages`, `can_delete_messages` tekshiriladi; yetmasa `PermissionMissingError(user_message_uz="Bot kanalda to'liq admin emas: ...")`.
- Obunachi soni: bot (`getChatMemberCount`). Ko'rish/reaksiya/ulashish/o'sish grafigi: faqat Telethon yo'li (`capability: ANALYTICS`).
- Raqobatchi ochiq kanal: `PublicChannelScraper(t.me/s/<handle>)` — `Connector`ning faqat `fetch_account_stats`, `fetch_posts` qismi; sessiyasiz; kamida 3–5 soniya tanaffus.
- `TelethonReadOnlyClient` ochiq metodlar ro'yxati (whitelist): `get_entity`, `get_messages`, `iter_messages`, `get_stats` (broadcast stats), `get_participants_count`. Boshqasi yo'q.

**Instagram (`InstagramConnector`)** — Meta Graph API.
- `Credentials`: uzoq muddatli token (shifrlangan), `expires_at`, `ig_user_id`, `page_id` (agar yo'l talab qilsa).
- `refresh_credentials` muddatidan **7 kun** oldin job bilan chaqiriladi (`token_refresh`).
- Story: har soatlik `story_snapshot` job; story chiqmaguncha (24 soat) davomida yozib boriladi, tugagach `is_final=True` qator.
- Nashr oqimi: `create_container` → `poll_status` (2–5 s intervalda, max 5 daqiqa; video uchun 10) → `media_publish`. Kunlik nashr limiti `limits.publish_per_day` dan oshmaydi.
- Video yuklash: avval **resumable upload** (to'g'ridan-to'g'ri fayl), ishlamasa `video_url` (R2) zaxira yo'li (§9.4). `Settings.publish.use_r2` = `auto|always|never`.

**YouTube (`YouTubeConnector`)** — Data API v3 + Analytics + Upload.
- `Credentials`: refresh token (shifrlangan). Google loyihasi **Production** rejimida bo'lishi kerak (aks holda token 7 kunda o'ladi); `health_check` buni aniqlay olmaydi, shuning uchun setup qo'llanmasida qizil ogohlantirish bo'ladi.
- Kvota hisobi: har bir chaqiruv `quota_cost` bilan `provider_usage_log`ga yoziladi (`search.list`=100, `videos.insert`=1600, `list`=1 va h.k., qiymatlar `settings`da yangilanadi). Kunlik limit Pacific vaqti bo'yicha tiklanadi.
- `publish`: `videos.insert` (resumable), `privacyStatus`; audit holatida video yopiq bo'lib qolsa, `PublishResult.raw["audit_restricted"]=True` va UI'da sariq ogohlantirish.

---

## 3. DataProvider shartnomasi (ochiq ma'lumot / raqobatchi)

Connector — **o'z** akkaunt, DataProvider — **boshqalarning ochiq** ma'lumoti. Ikkalasi alohida.

```python
class DataKind(StrEnum):
    PROFILE = "profile"; POSTS = "posts"; VIDEO_LIST = "video_list"
    COMMENTS = "comments"; TRANSCRIPT = "transcript"

class DataProvider(Protocol):
    name: str                                   # "youtube_data_api" | "scrapecreators" | "tme_public" | ...
    supports: dict[Platform, set[DataKind]]
    def estimate_cost(self, platform: Platform, kind: DataKind, count: int) -> "Cost": ...
    def fetch(self, req: "DataRequest") -> "DataResponse": ...
    def status(self) -> "ProviderStatus": ...    # qoldiq kvota/kredit, ishlayaptimi

@dataclass(frozen=True)
class DataRequest:
    platform: Platform; kind: DataKind; target: str          # handle yoki URL
    limit: int = 20; cursor: str | None = None
    max_cost: "Cost | None" = None                            # per-run cap
    cache_max_age_sec: int | None = None

@dataclass(frozen=True)
class Cost:
    unit: str            # "quota_units" | "credits"
    amount: float

@dataclass(frozen=True)
class DataResponse:
    provider: str; data: Any; cost: Cost; from_cache: bool; fetched_at: datetime
```

### 3.1. ProviderRouter (failover)

```python
class ProviderRouter:
    def fetch(self, req: DataRequest) -> DataResponse: ...
```
Tartib: `settings.providers.priority[platform][kind]` ro'yxati. Har bir nomzod uchun:
1. `enabled` va `cooldown` tugagan, va kunlik/oylik chegaradan oshmagan bo'lishi kerak.
2. `estimate_cost` > `req.max_cost` bo'lsa o'tkazib yuboriladi.
3. Muvaffaqiyatli → `provider_usage_log` yoziladi, qaytadi.
4. `QuotaExceededError` / limit chegarasi (`quota_switch_pct`, sukut 90%) / kredit `credit_warn_threshold`dan past → keyingisiga o'tadi, `provider_failover_events`ga sabab yoziladi, bildirishnoma (dedup bilan).
5. `RateLimitError`/blok → provayder `cooldown_until` ga qo'yiladi.
6. Hammasi tugasa → `NoProviderAvailable`: job `run_at = ertaga 00:05 Pacific` ga ko'chadi, admin bildirishnomasi.
7. Provayder tiklanganda (cooldown/yangi kun) priority tartibiga avtomatik qaytadi (maxsus "sticky" holat yo'q).

**ScrapeCreators qo'shimcha:** `mode: free|paid` (sozlama). Har so'rovda `cache_max_age` yuboriladi. Kredit qoldig'i har javobdan keyin yangilanadi. `daily_credit_cap`, `monthly_credit_cap`, `per_run_credit_cap`. Chegara ichidagi hisob: `days_left = remaining / avg_daily_spend(7 kun)`.

---

## 4. AI Router shartnomasi

```python
class TaskType(StrEnum):
    LONG_UZ = "long_uz"                 # plan, ssenariy, tahlil xulosasi
    CLASSIFY = "classify"               # sentiment, izoh turi, teglar
    VISION = "vision"                   # kadr/rasm tahlili
    STT = "stt"                         # audio → matn
    BRAND_PROFILE = "brand_profile"
    SCRIPT_REVIEW = "script_review"
    COMMENT_REPLY = "comment_reply"
    WHY_WORKED = "why_worked"
    AD_PLAN = "ad_plan"

@dataclass(frozen=True)
class AIRequest:
    task: TaskType
    business_id: int | None
    system_extra: str | None            # brend xotirasi router tomonidan avtomatik qo'shiladi
    prompt: str
    attachments: list["Attachment"] = field(default_factory=list)   # rasm/audio
    response_schema: dict | None = None  # JSON schema
    priority: int = 5                    # 1 = nashrga aloqador (eng yuqori)
    cache_ttl_sec: int | None = 86400
    require_lang: str | None = "uz"

@dataclass(frozen=True)
class AIResult:
    text: str | None
    data: dict | None                    # schema bo'yicha validatsiya qilingan
    provider: str; model: str; key_alias: str
    tokens_in: int; tokens_out: int
    cost_usd: Decimal                    # bepul bo'lsa 0
    from_cache: bool
    lang_check: "LangCheck | None"

class AIProvider(Protocol):
    name: str
    def supports(self, task: TaskType) -> bool: ...
    def call(self, req: AIRequest, key: "ApiKey", model: str) -> "RawAIResponse": ...
```

**Marshrut jadvali** (`ai_routes`): `task → [ {provider, model, enabled, paid: bool}, ... ]`. Boshlang'ich qiymatlar TZ 4.11 jadvali bo'yicha. `paid=True` yozuvlar faqat §4.2 qoidasiga ko'ra ishlaydi.

### 4.1. Almashish va cooldown
- `429`, `quota`, `timeout`, `5xx`, bo'sh/yaroqsiz javob → keyingi **kalit** (shu provayder), kalitlar tugasa keyingi **provayder**.
- Muvaffaqiyatsiz kalit `cooldown_until = now + backoff` (60s → 5m → 30m → 2h, muvaffaqiyatda qayta o'rnatiladi). `ai_usage_log`da har urinish.
- Kalit tanlash: round-robin, cooldown'dagilar o'tkazib yuboriladi; kunlik/minutlik limitga 90% yetganlar oxirgi o'ringa tushadi.
- Hamma yo'l yopiq bo'lsa `AIUnavailable`; job `retry`ga ketadi (nashrga aloqador bo'lmasa tungi navbatga ko'chirish mumkin).

### 4.2. Pullik rejim (Claude)
```
settings.ai.paid.enabled        = false   # sukut
settings.ai.paid.monthly_budget_usd
settings.ai.paid.policy         = "only_when_free_exhausted" | "only_complex" | "always"
```
- `enabled=false` bo'lsa pullik marshrut **ko'rilmaydi ham**.
- Byudjet tugasa pullik marshrut o'chadi, admin xabardor qilinadi.
- `only_complex`: `TaskType in {LONG_UZ, SCRIPT_REVIEW, AD_PLAN, BRAND_PROFILE}` yoki oldingi bepul urinish til tekshiruvidan o'tmagan.

### 4.3. Kesh
Kalit: `sha256(task + model_family + canonical(prompt) + attachments_hash + brand_version)`. `ai_cache(key, result, expires_at)`. Kesh javobi `from_cache=True`, kvota sarflamaydi.

### 4.4. Maxfiylik
`AIRequest.prompt` router kirishida `SecretScrubber`dan o'tadi (token, parol, kalit, telefon formatidagi sirlar). Topilsa maskalanadi va audit yoziladi.

### 4.5. Til tekshiruvi (`require_lang="uz"`)
Evristika: kirill/lotin nisbati, o'zbekcha stop-so'zlar ulushi, rus/ingliz so'zlar ulushi chegarasi. `LangCheck{ok: bool, score: float, reason}`. `ok=False` → bir pog'ona yuqori marshrutga qayta yuboriladi (maks 1 marta), natija baribir `lang_check.ok=False` belgisi bilan inson ko'rigiga tushadi.

---

## 5. Job (fon vazifalari) shartnomasi

### 5.1. Jadval — TZ 3.3 dagidek. Qo'shimcha: `queue` (`collect|ai|media|publish|system`), `dedupe_key` (UNIQUE bilan faol job'lar uchun), `business_id` (nullable), `progress` (0–100), `result` (JSON).

### 5.2. Interfeys
```python
def enqueue(job_type: str, payload: dict, *, queue: str, priority: int = 5,
            run_at: datetime | None = None, dedupe_key: str | None = None,
            business_id: int | None = None, max_attempts: int = 3) -> int: ...

JobHandler = Callable[[JobContext], None]     # JobContext: payload, report_progress(pct), log(msg), is_cancelled()
register_handler(job_type, handler)           # apps/<app>/jobs.py ichida
```
Qoidalar: handler **idempotent**; `retryable` xato → eksponensial (1/5/15 daqiqa), `max_attempts` dan keyin `failed` + bildirishnoma; `NoProviderAvailable` → `run_at` kechiktiriladi (urinish sanalmaydi); worker heartbeat har 10 s; `locked_at` > 10 daqiqa (yoki `media` uchun 60) bo'lsa job qaytariladi.

### 5.3. Navbatlar va oqimlar
`publish` (ustuvorlik eng yuqori, 2 oqim) · `collect` (3) · `ai` (2) · `media` (1) · `system` (1). Qiymatlar `settings.jobs.workers.*`.

### 5.4. Job turlari va payload'lar

| `job_type` | queue | payload | Izoh |
|---|---|---|---|
| `collect_account` | collect | `{connection_id, mode: "regular"\|"history", days?}` | o'z akkaunt statistikasi/postlari |
| `collect_post_metrics` | collect | `{connection_id, post_ids?, window: "1h\|6h\|24h\|72h\|7d\|30d"}` | o'sish egri chizig'i |
| `story_snapshot` | collect | `{connection_id}` | har soat |
| `collect_comments` | collect | `{connection_id, since}` | |
| `collect_competitor` | collect | `{competitor_id, depth: "light"\|"full"}` | `light` = profil |
| `historical_import` | collect | `{connection_id, days:90}` | progress ko'rsatadi |
| `token_refresh` | system | `{connection_id}` | |
| `health_probe` | system | `{scope: "connection\|provider\|server"}` | |
| `ai_task` | ai | `{request: AIRequest (serialized), callback: {type, id}}` | natija `ai_generations`ga |
| `post_insight` | ai | `{post_id}` | "nega ishladi" |
| `media_analyze` | media | `{media_file_id}` | gibrid pipeline |
| `publish_item` | publish | `{content_item_id, platform}` | §9 |
| `r2_cleanup` | system | `{}` | har soat |
| `report_generate` | system | `{business_id, kind, period, deliver: bool}` | |
| `report_deliver` | system | `{report_id}` | bot orqali |
| `link_sync` | system | `{}` | Worker'dan kliklarni olish |
| `notify_dispatch` | system | `{notification_id}` | |

---

## 6. RBAC shartnomasi

### 6.1. Ruxsat kodi: `<module>.<action>`
**Modullar** (TZ 2.3): `dashboard, businesses, connections, competitors, analytics, calendar, publish, approvals, ai_studio, scripts, media_analysis, hooks, comments, ads, reports, links, notifications, system_health, settings, users`.
**Amallar:** `view, create, edit, delete, approve, publish, export, configure`.
Barcha mumkin kodlar `apps/accounts/permissions_registry.py`da bitta ro'yxatda; bo'lmagan kodni ishlatish import vaqtida xato beradi.

### 6.2. Hisoblash
```
effective(user, business) =
    (role_permissions[ user_business_access(user,business).role ]
     + user_permission_overrides.allow) - user_permission_overrides.deny
Admin → hamma narsa, hamma biznes.
```
```python
class PermissionService:
    def can(self, user, code: str, business: "Business | None" = None) -> bool: ...
    def businesses_for(self, user, code: str | None = None) -> QuerySet: ...
```
- Keshlanadi, lekin ruxsat o'zgarganda darhol bekor qilinadi (qayta kirish talab qilinmaydi).
- `@require_permission("calendar.approve")` biznesni so'rov kontekstidan (`request.business`) oladi; biznes kirishi yo'q bo'lsa 404 (mavjudligini ham oshkor qilmaydi).
- Biznesga bog'lanmagan modullar (`settings`, `users`, `system_health`) uchun `business=None`.

### 6.3. Himoya qoidalari
Admin o'zini o'chira/pasaytira olmaydi; oxirgi faol admin o'chmaydi; rolni o'chirish uchun foydalanuvchilar ko'chirilgan bo'lishi kerak.

---

## 7. Kontent holat mashinasi

```
draft ──submit──▶ pending_approval ──approve──▶ approved ──schedule──▶ scheduled
  ▲                    │ reject                                      │  (vaqt keldi)
  └────────────────────┘                                             ▼
                                                              publishing ──▶ published
                                                                  │
                                                                  └──▶ failed ──retry──▶ scheduled
```
| Holat (kod) | O'zbekcha | Kim o'tkaza oladi |
|---|---|---|
| `draft` | Qoralama | `calendar.create/edit` |
| `pending_approval` | Tasdiqlash kutilmoqda | `calendar.edit` (submit) |
| `approved` | Tasdiqlandi | `approvals.approve` (+ mijoz tasdig'i yoqilgan bo'lsa `client_approved`) |
| `scheduled` | Rejalashtirildi | avtomatik (tasdiqdan keyin vaqt qo'yilganda) |
| `publishing` | Nashr qilinmoqda | faqat worker |
| `published` | Chiqarildi | faqat worker |
| `failed` | Xato | faqat worker; `publish.publish` bilan qo'lda `retry` |

Qoidalar:
- Faqat `scheduled` (va `approved_by` mavjud, `rule_check.status != blocked`, `ai_draft_reviewed=True` agar AI yozgan bo'lsa) element `publish_item` job'iga aylanadi.
- Tasdiqdan keyin matn/media tahrirlansa → holat `pending_approval`ga qaytadi (yangi tasdiq).
- Biznes yoki ulanish `kill_switch=True` bo'lsa, `scheduled` elementlar nashr qilinmaydi, `blocked_by_kill_switch` belgisi bilan kutadi.
- Har bir o'tish `audit_logs` va (kerak bo'lsa) bildirishnoma hosil qiladi.
- Ko'p tarmoqli element: har tarmoq uchun alohida `publish_attempts` holati; umumiy holat `published` faqat hammasi muvaffaqiyatli bo'lsa, qisman bo'lsa `partial` (UI belgisi), `failed` qismini qayta urinish mumkin.

---

## 8. Content Rules shartnomasi

### 8.1. Interfeys
```python
class RuleSeverity(StrEnum):
    PASS = "pass"; WARN = "warn"; BLOCK = "block"

@dataclass(frozen=True)
class RuleProblem:
    rule_id: str; severity: RuleSeverity
    message_uz: str; field: str | None = None; suggestion_uz: str | None = None

class ContentRule(Protocol):
    id: str; category: str       # brand|platform|truth|originality|policy|language
    def check(self, item: "ContentItemSnapshot", ctx: "RuleContext") -> list[RuleProblem]: ...

def run_rules(item, platform) -> "RuleCheckResult":    # status = max severity
```
`RuleCheckResult.status`: `pass` | `warn` | `block`. `block` nashrni to'sadi (override mumkin emas); `warn` — `publish.publish` + `approvals.approve` huquqi bor foydalanuvchi "Baribir davom etish"ni asoslab tasdiqlashi mumkin (audit'ga sabab bilan yoziladi).

### 8.2. Boshlang'ich qoidalar
| id | Kategoriya | Sukut daraja | Tekshiruv |
|---|---|---|---|
| `brand.banned_words` | brand | block | taqiqlangan so'z |
| `brand.required_words` | brand | warn | majburiy so'z/CTA |
| `brand.emoji_level` | brand | warn | emoji miqdori |
| `platform.text_length` | platform | block | TG 4096/1024 (media caption), IG 2200, YT title 100 / desc 5000 |
| `platform.hashtag_count` | platform | warn | IG ≤ 30 (tavsiya ≤ 10), YT ≤ 15 |
| `platform.video_spec` | platform | block | nisbat, davomiylik (Reels ≤ 3 daq, Shorts ≤ 3 daq, Stories ≤ 60 s), hajm, kodek |
| `platform.image_spec` | platform | block | o'lcham/nisbat/hajm |
| `truth.facts_match` | truth | block | narx/chegirma/muddat/telefon/manzil biznes ma'lumotiga mos |
| `truth.unverified_claim` | truth | warn | "100% kafolat", "eng arzon" kabi da'volar |
| `orig.competitor_similarity` | originality | block ≥0.85, warn ≥0.7 | raqobatchi/hook matniga o'xshashlik (n-gram Jaccard + embedding ixtiyoriy) |
| `policy.sensitive_topic` | policy | warn | sog'liq/moliya va'dalari |
| `policy.copyright_media` | policy | warn | musiqa/rasm manbasi belgilanmagan |
| `lang.orthography_uz` | language | warn | imlo/uslub (lotin, apostrof `ʻ`/`'` birligi) |
| `ai.draft_not_reviewed` | language | block | AI qoralamasi inson ko'rmagan |

### 8.3. `dry_run` ham shu `RuleProblem` formatini ishlatadi (connector darajasidagi tekshiruvlar: ruxsat, fayl formati).

Qoida to'plami biznes darajasida: `content_rule_sets(business_id, rule_id, enabled, severity_override, params)`. `block`dan pastga tushirish faqat `truth.*` va `ai.draft_not_reviewed` uchun **mumkin emas**.

---

## 9. Nashr shartnomasi

### 9.1. `publish_item` oqimi
```
1. Qulflash: content_item(platform) uchun publish_attempts qatori (UNIQUE idempotency_key) yaratiladi
2. Qayta tekshiruv: holat=scheduled, tasdiq, run_rules()!=block, kill_switch=False, connection ACTIVE
3. connector.dry_run()  → ok=False bo'lsa attempt=failed (retryable=False)
4. Media tayyorlash (§9.4)
5. connector.publish(req)
6. Muvaffaqiyat: attempt=success, external_id, url → posts jadvaliga kiritiladi,
   collect_post_metrics (1h/6h/24h/72h/7d/30d) navbatga qo'yiladi, R2 tozalash belgilanadi
7. Xato: retryable → eksponensial, max 3; retryable emas → failed + bildirishnoma
```
Takroriy nashr himoyasi: 1-bosqichda `idempotency_key` mavjud va `success` bo'lsa job darhol tugaydi; mavjud `publishing` bo'lsa va `locked_at` yangi bo'lsa kutadi; tarmoqda "oxirgi post matni mos keladi" tekshiruvi `publish()` boshida (TG/YT uchun).

Vaqt: `scheduled_at` o'tib ketib, nashr qilib bo'lmagan bo'lsa (internet uzilishi), `settings.publish.late_policy`: `publish_if_within_min` (sukut 30) — undan kech bo'lsa nashr qilinmaydi, `failed(reason="missed_window")`, admin xabardor qilinadi.

### 9.2. Kill switch
`businesses.autopublish_enabled`, `social_accounts.autopublish_enabled`. Ikkalasi `True` bo'lsagina nashr. Qo'lda (UI'dagi) bir tugma bilan o'chiriladi, audit'ga tushadi.

### 9.3. Bildirishnomalar: `publish.success`, `publish.failed`, `publish.missed_window`, `publish.r2_full`.

### 9.4. Media uzatish va R2
- `settings.publish.use_r2 = auto | always | never` (sukut `auto`).
- `auto`: connector `capabilities`da `DIRECT_UPLOAD` bo'lsa to'g'ridan-to'g'ri; yo'q bo'lsa yoki yuklash muvaffaqiyatsiz bo'lsa R2.
- R2 qoidalari (TZ FR-K6): yuklash `publish_at − lead_min` (30–60), muvaffaqiyatda **o'sha tarmoqlar hammasi** tugagach o'chiriladi, jami hajm `r2.max_gb` (sukut 9) dan oshmaydi (yuklashdan oldin `r2_objects` yig'indisi + yangi fayl tekshiriladi), joy yo'q bo'lsa job `waiting_r2` holatida kutadi + bildirishnoma, xatoda `r2.keep_failed_hours` saqlanadi, `r2_cleanup` yetim fayllarni (`r2_objects`da yo'q yoki eskirgan) o'chiradi.
- Asl fayllar `media_store/` (lokal disk)da qoladi, saqlash muddati `settings.media.retention_days`.

---

## 10. Media tahlil shartnomasi

```python
@dataclass
class MediaAnalysisResult:
    file_hash: str
    technical: dict      # duration, fps, resolution, aspect, scene_count, cuts_per_min, has_face_ratio, dominant_colors, ocr_text?
    transcript: "Transcript | None"       # text, lang, confidence, provider
    ai: dict | None      # hook, visual_quality, pacing, cta, brand_fit, suggestions (JSON schema)
    degraded: bool       # bulutli AI bo'lmaganda True
    took_sec: float
```
Pipeline qadamlari alohida funksiya (`probe`, `scenes`, `keyframes`, `audio_extract`, `stt`, `vision_summary`), har biri natijasini keshlaydi (`media_analyses.step_results`). Bulutli AI **bitta so'rov** (kadrlar + transkript + metadata). STT: avval `stt` marshruti (Groq Whisper), zaxira faster-whisper. O'zbekcha transkript `confidence` past bo'lsa tahlilda "ishonchsiz" deb belgilanadi va AI promptida shu ko'rsatiladi.

---

## 11. Tahlil va reklama formulalari (shaffof)

### 11.1. Metrikalar
- `ER_post = (likes + comments + shares + saves) / reach` (reach yo'q bo'lsa `views`, yo'q bo'lsa `followers` — qaysi maxraj ishlatilgani `er_basis` maydonida yoziladi).
- `ER_account(period) = mean(ER_post)` (vaznli: reach bo'yicha).
- O'sish: `followers_delta`, `followers_growth_pct`.
- "Ishladi" mezoni: `ER_post` va `views` biznesning oxirgi 30 kunlik medianasidan > `settings.analytics.winner_multiplier` (sukut 1.5).
- Anomaliya: `z-score` (rolling 28 kun) `|z| ≥ 2.5` yoki kunlik o'zgarish `≥ ±X%` (sozlanadi).

### 11.2. Sotuv prognozi (`AdForecast`)
```
impressions = budget / cpm * 1000
clicks      = impressions * ctr
leads       = clicks * click_to_lead
sales       = leads * lead_to_sale
revenue     = sales * avg_check
roi         = (revenue * margin_or_1 - budget) / budget
```
Har bir koeffitsiyent: `{value, source: "own_history"|"industry_template"|"manual"|"calibrated", sample_size}`. Uch stsenariy: past = P25, o'rtacha = P50, yuqori = P75 (tarix yetarli bo'lmasa andoza diapazoni). Real natija kiritilganda `calibrated` manbaga o'tadi (eksponensial silliqlash, `alpha` sozlanadi). UI har doim "Taxminiy prognoz" yozuvini ko'rsatadi. AI faqat **izoh va kampaniya matni** yozadi, raqamlarni kod hisoblaydi.

### 11.3. Reklama nomzodi balli
`ad_score = w1*z(ER) + w2*z(saves+shares) + w3*z(watch_time) + w4*recency_bonus`, vaznlar `settings.ads.score_weights`; faqat `age ≥ min_age_hours` (sukut 24) postlar; yoqish vaqti tavsiyasi — posting tarixi va kun/soat bo'yicha o'rtacha ER'dan.

---

## 12. Sozlamalar kalitlari (`system_settings`)

Format: `key` (nuqtali), `value` (JSON), `is_secret` (bool), `scope` (`global|business|connection`), `updated_by`, `updated_at`. Sirlar Fernet bilan.

| Kalit | Sukut | Izoh |
|---|---|---|
| `general.system_name` | "SMM Platforma" | |
| `general.theme_default` | "light" | |
| `general.brand_color` | "#E11D2E" | |
| `general.timezone` | "Asia/Tashkent" | |
| `server.host` | "0.0.0.0 (lokal interfeys)" | `.env`dan |
| `collect.schedule` | `["08:00","12:00","17:00","21:00"]` | umumiy; biznes/ulanish override |
| `collect.history_days` | 90 | |
| `collect.story_snapshot_minutes` | 60 | |
| `collect.post_metric_windows` | `["1h","6h","24h","72h","7d","30d"]` | |
| `providers.priority.youtube.*` | `["youtube_data_api","scrapecreators"]` | har DataKind uchun |
| `providers.quota_switch_pct` | 90 | |
| `providers.youtube_data_api.daily_quota` | 10000 | |
| `scrapecreators.mode` | "free" | free/paid |
| `scrapecreators.credit_warn_threshold` | 20 | |
| `scrapecreators.per_run_cap` / `daily_cap` / `monthly_cap` | 10 / 50 / 500 | boshlang'ich taxminiy; real kreditga qarab |
| `competitors.light_per_day` / `heavy_per_week` | 3 / 1 | |
| `telethon.daily_request_cap` | 500 | |
| `telethon.min_delay_sec` | 2 | |
| `ai.keys.<provider>[]` | — | sir, ko'p kalit |
| `ai.routes.<task>` | TZ 4.11 jadvali | |
| `ai.paid.enabled` | false | |
| `ai.paid.policy` / `monthly_budget_usd` | "only_when_free_exhausted" / 0 | |
| `ai.cache.default_ttl_sec` | 86400 | |
| `publish.use_r2` | "auto" | |
| `publish.r2.max_gb` | 9 | qattiq chegara 9.5 dan oshmaydi |
| `publish.r2.lead_min` | 45 | |
| `publish.r2.keep_failed_hours` | 24 | |
| `publish.late_policy_min` | 30 | |
| `publish.max_attempts` | 3 | |
| `youtube.upload_daily_cap` | 6 | kvotaga qarab avtomatik hisoblanadi |
| `jobs.workers.<queue>` | 2/3/2/1/1 | |
| `jobs.lock_timeout_min` | 10 | |
| `notify.mandatory` | `["publish.failed","token.expiring","quota.exhausted"]` | |
| `notify.dedupe_minutes` | 30 | |
| `security.session_hours` | 12 | |
| `security.lockout_attempts` | 5 | |
| `reports.brand.logo` / `reports.brand.color` | — | |
| `media.retention_days` | 90 | |
| `media.local_whisper_model` | "small" | int8 |
| `ads.score_weights` | `{...}` | |
| `analytics.winner_multiplier` | 1.5 | |

---

## 13. Bildirishnoma shartnomasi

`notifications(id, user_id, business_id, type, severity[info|warn|critical], title_uz, body_uz, link, dedupe_key, created_at, read_at, delivered_channels[])`.
Turlari (kod → majburiy emas/majburiy): `task.assigned`, `approval.requested`, `content.status_changed`, `publish.success`, `publish.failed` (M), `quota.warning`, `quota.exhausted` (M), `token.expiring` (M), `anomaly.detected`, `comment.negative`, `report.ready`, `provider.switched`, `r2.full`.
`dedupe_key` + `notify.dedupe_minutes` ichida takrorlanmaydi (guruhlanadi: "5 ta o'xshash xato").
Kanallar: `web`, `telegram` (xodim Telegram ID'si bog'langan bo'lsa). Foydalanuvchi sozlaydi, majburiy turlarni admin belgilaydi.

---

## 14. Telegram bot (mijoz kabineti) shartnomasi

- Bog'lash: `/start <kod>`. `client_invites(code_hash, business_ids[], created_by, expires_at, used_at)`; kod bir martalik, muddatli; ulangach `client_bot_users(tg_user_id, business_ids[], allowed_sections[], active)`.
- Har bir bot handler boshida: `tg_user_id` → faol `client_bot_users` → kirish huquqi → biznes tanlash. Veb-platformaga kirish ma'lumotlari bu yo'ldan berilmaydi.
- Bo'limlar (`allowed_sections`, biznes kesimida): `report_weekly`, `report_monthly`, `kpi`, `top_posts`, `content_plan`, `approve_posts`, `report_issue`.
- `approve_posts`: mijoz rejadagi postni `approved` / `changes_requested` (izoh bilan) qiladi; `changes_requested` → element `draft`ga qaytadi + SMM bildirishnomasi.
- Mijozga **hech qachon** ko'rsatilmaydi: ichki izohlar, raqobatchi tahlili (agar yoqilmasa), boshqa bizneslar, AI kalit/provayder ma'lumoti, xarajat/kvota.

---

## 15. Havolalar (Cloudflare Worker)

```
short_links(id, business_id, slug UNIQUE, target_url, utm JSON, content_item_id?, campaign_id?, expires_at?, enabled)
link_clicks(id, link_id, clicked_at, source_hint, device_class[mobile|desktop|tablet|bot], country?)
```
Worker API (token bilan, tizim chaqiradi): `PUT /admin/links/{slug}`, `DELETE /admin/links/{slug}`, `GET /admin/stats?since=`. Tashqi OAuth callback sahifasi ham shu Worker'da: `GET /oauth/{provider}/callback` → `code`/`state` ni lokal manzilga (`state` ichida shifrlangan) brauzer orqali yo'naltiradi; Worker kodni saqlamaydi, loglamaydi. Klik IP'si saqlanmaydi (faqat umumiy qurilma turi/davlat).

---

## 16. Ichki API (DRF) konventsiyalari

- Prefiks `/api/v1/`, JSON, sahifalash `cursor`, xato formati:
```json
{ "error": { "code": "permission_denied", "message_uz": "Bu amalga ruxsat yo'q.", "details": {} } }
```
- HTTP: 400 validatsiya, 401 kirmagan, 403 ruxsat yo'q, 404 topilmadi (biznes kirishi yo'q ham), 409 holat mos emas (masalan, noto'g'ri o'tish), 422 qoida bloklagan (`RuleCheckResult` bilan), 429 limit.
- Asosiy resurslar (CRUD + amallar): `businesses`, `businesses/{id}/brand-profile` (+`versions`, `restore`), `connections`, `connections/{id}/test`, `competitors`, `content-items` (`submit`, `approve`, `reject`, `schedule`, `retry`, `check-rules`), `plans`, `scripts` (`analyze`), `hooks`, `comments` (`suggest-reply`, `send-reply`), `ads/recommendations`, `ads/campaigns`, `ads/forecast`, `reports` (`generate`, `download`), `links`, `jobs` (ko'rish, bekor qilish), `health`, `settings`, `users`, `roles`, `audit-logs`.
- Idempotent yozish uchun `Idempotency-Key` sarlavhasi (nashr/hisobot yaratish amallarida).

---

## 17. Xato kodlari (foydalanuvchiga ko'rinadigan, o'zbekcha matn bilan)

| Kod | Qachon | Xabar (qisqa) |
|---|---|---|
| `permission_denied` | RBAC | Bu amalga ruxsat yo'q |
| `business_forbidden` | biznes kirishi | Bu biznesga kirish huquqingiz yo'q |
| `bot_not_admin` | TG ulanish | Bot kanalda to'liq admin emas |
| `token_expired` | OAuth | Ulanish muddati tugagan, qayta ulang |
| `quota_exhausted` | provayder | Kunlik limit tugadi; ertaga davom etadi |
| `credit_low` | ScrapeCreators | Kredit kam qoldi |
| `rule_blocked` | Content Rules | Qoida bo'yicha nashr to'xtatildi: … |
| `not_approved` | nashr | Kontent tasdiqlanmagan |
| `kill_switch_on` | nashr | Avtonashr to'xtatilgan |
| `r2_full` | R2 | Vaqtinchalik saqlash joyi to'lgan |
| `ai_unavailable` | AI | AI xizmati vaqtincha mavjud emas |
| `invalid_state_transition` | holat | Bu holatdan o'tish mumkin emas |
| `invite_invalid` | bot | Taklif kodi yaroqsiz yoki muddati tugagan |

---

## 18. Ma'lumotlar bazasi tamoyillari (TZ 7 ga qo'shimcha)

- Har bir biznesga tegishli jadval: `business_id` NOT NULL + indeks; murakkab so'rovlar uchun `(business_id, <vaqt>)` kompozit indeks.
- Metrika jadvallari: `(connection_id|post_id, taken_at)` UNIQUE-yaqin indeks; INSERT-only.
- `social_accounts.encrypted_credentials` (BLOB), `key_version` (Fernet kalit aylantirish uchun `MultiFernet`).
- `jobs`: `(status, queue, run_at, priority)` indeksi; `dedupe_key` uchun filtrlangan UNIQUE (faqat `pending|running`).
- `audit_logs`: faqat INSERT; DB foydalanuvchisiga UPDATE/DELETE huquqi berilmaydi (iloji bo'lsa trigger bilan himoya).
- Soft-delete: `archived_at` (ulanish, biznes, kontent). Qattiq o'chirish faqat admin va audit bilan.

---

## 19. Test shartnomalari

- `FakeConnector`, `FakeDataProvider`, `FakeAIProvider`, `FakeClock` — barcha real adapterlar bilan bir xil kontrakt test to'plamidan o'tadi (`tests/contracts/`).
- `USE_FAKES=1` — kalitsiz to'liq demo ma'lumot (3 ta namuna biznes: o'quv markaz, kiyim do'koni, kompyuter xizmatlari; har birida TG/IG/YT fixture'lari).
- Majburiy senariy testlar: (1) ruxsatsiz foydalanuvchi boshqa biznesga API orqali kira olmaydi; (2) `draft` kontent nashr job'iga aylanmaydi; (3) bir xil `idempotency_key` ikki nashr bermaydi; (4) YouTube kvotasi tugasa ScrapeCreators'ga, ikkalasi tugasa ertaga ko'chadi; (5) AI kalit 429 → keyingi kalit → keyingi provayder; Claude `enabled=false` da chaqirilmaydi; (6) R2 hajmi 9 GB dan oshmaydi; (7) Telethon wrapper whitelist'dan tashqari metodni rad etadi; (8) sirlar loglarda va AI promptida yo'q.


---

# v1.0 — Yakuniy qarorlar va farqlar (amalga oshirish bilan kelishilgan)

Bu bo'lim yuqoridagi matnni **bekor qiladi**, agar ziddiyat bo'lsa.

1. **Instagram ulanishi — «Instagram Login»** (Facebook sahifasi shart emas). Scope: `instagram_business_basic`, `_content_publish`, `_manage_comments`, `_manage_insights`. Token: qisqa → uzoq (60 kun); ≥24 soatlik token muddatidan oldin `ig_refresh_token` bilan yangilanadi. Nashr: konteyner → holat so'rovi → `media_publish`; video `resumable upload` (ommaviy URL shart emas), rasm uchun ommaviy URL.
2. **Login/parol bilan ulanish YO'Q** (hech bir tarmoq uchun): faqat rasmiy OAuth / bot token. Telethon — faqat o'qish (whitelist), alohida SIM tavsiya, SafetyGuard (kechikish, kunlik limit, faol soatlar, FloodWait, 3 ketma-ket xatoda o'zini o'chirish).
3. **OAuth callback** — bitta bepul Cloudflare Worker: `/oauth/<provider>/callback` → faqat shaxsiy tarmoq/localhost manzillariga 302 (open-redirect himoyasi, kod saqlanmaydi). Zaxira: `oauth.callback_url` (masalan `http://localhost:8000`) — Google Worker URI'ni qabul qilmasa.
4. **YouTube** — OAuth ilova **Production** holatida (refresh token 7 kunda o'lmaydi); yuklash kvotasi 1600/video (~6/kun); `invalid_grant` → «Qayta ulash».
5. **Vaqtinchalik hosting** — birlamchi: **Worker KV** (admin API `/admin/tmp/{key}?ttl=`, ≤24 MB); R2 ixtiyoriy zaxira (9 GB chegara). Video/Reels/Stories hosting talab qilmaydi (resumable upload). Sozlama: `publish.use_r2 = auto|worker_kv|r2`.
6. **STT zanjiri** — Groq Whisper (`uz`, prompt) → Gemini audio → lokal `faster-whisper`; past ishonch «qisman natija» deb belgilanadi.
7. **Claude (pullik) standart O'CHIQ**; yoqilsa oylik byudjet + siyosat (`only_when_free_exhausted | quality_tasks | always`).
8. **Zaxira** — kunlik `backup_db` (~03:30), `smm_YYYYMMDD_HHMM.sql.gz` + `env_….backup`, saqlash `backup.keep_days`.
9. **Veb** — React SPA (`frontend/`, `/app/`) + Django JSON view'lari (`apps/web/spa.py`, `ui.py` bloklar tizimi). Ichki API: `/api/v1/session/|health|businesses|notifications/unread`.
10. **Yo'riqnoma** — `docs/setup/*.md` ilova ichida «Yo'riqnoma» bo'limida ko'rsatiladi (birinchi qator `# Sarlavha`).
11. **Ishga tushirish** — `run.bat` → `tools/supervisor.py` (veb `manage.py serve` (Waitress) + `manage.py worker`, watchdog `/api/v1/health/`). Sozlash ustasi `tools/first_run.py`.
12. **Ruxsat presetlari** — `settings`, `users`, `system_health` modullari «ko'rish» presetlariga kirmaydi (faqat admin yoki alohida berilganda).
13. **USE_FAKES=1** — barcha connector, AI va ochiq-ma'lumot provayderlari soxta (kalitsiz demo va testlar; tashqi tarmoqqa chiqmaydi).
