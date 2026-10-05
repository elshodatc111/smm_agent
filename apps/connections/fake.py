"""FakeConnector: kalitsiz to'liq demo va testlar uchun (deterministik)."""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from .base import (AccountInfo, AccountStats, Capability, CommentData, Credentials, DryRunReport,
                   HealthResult, LimitProfile, MediaType, Page, Platform, PostData, PostMetrics,
                   PublishRequest, PublishResult, RuleProblem)

PUBLISHED: dict[str, PublishResult] = {}   # idempotency_key -> natija (jarayon ichida)
PUBLISH_CALLS: list[str] = []
FAIL_NEXT_PUBLISH: list[Exception] = []    # testlar: ketma-ket xatolar
DELETED: list[str] = []


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


class FakeConnector:
    capabilities = {Capability.STATS, Capability.POSTS, Capability.COMMENTS, Capability.STORIES,
                    Capability.PUBLISH, Capability.ANALYTICS, Capability.DIRECT_UPLOAD}
    limits = LimitProfile(min_interval_sec=0, jitter_sec=0, publish_per_day=100)

    def __init__(self, account=None, platform: str | Platform = "telegram", external_id: str = "fake1"):
        self.platform = Platform(account.platform if account else platform)
        self.external_id = (account.external_id or f"fake-{account.pk}") if account else external_id
        self.now = lambda: datetime.now(timezone.utc)

    def connect(self, credentials: Credentials) -> AccountInfo:
        return AccountInfo(self.external_id, f"@{self.external_id}", f"Demo {self.platform}", self._followers(0))

    def _followers(self, days_ago: int) -> int:
        base = 1000 + _rng(self.external_id).randint(0, 9000)
        return base + int((30 - min(days_ago, 30)) * base * 0.004)

    def health_check(self) -> HealthResult:
        return HealthResult(True, "Ishlayapti (demo)", self.now() + timedelta(days=50))

    def fetch_account_stats(self) -> AccountStats:
        r = _rng(self.external_id, self.now().strftime("%Y%m%d%H"))
        f = self._followers(0) + r.randint(-3, 12)
        return AccountStats(self.now(), f, posts_count=40, reach=f * 3 + r.randint(0, 500),
                            views=f * 4 + r.randint(0, 900), impressions=f * 5, profile_visits=r.randint(20, 300))

    def _posts(self) -> list[PostData]:
        out = []
        types = [MediaType.IMAGE, MediaType.REEL, MediaType.VIDEO, MediaType.TEXT]
        if self.platform == Platform.YOUTUBE:
            types = [MediaType.VIDEO, MediaType.SHORT]
        for i in range(24):
            r = _rng(self.external_id, i)
            t = types[i % len(types)]
            out.append(PostData(
                external_id=f"{self.external_id}-p{i}", media_type=t,
                text=f"Demo post #{i}: " + r.choice(["Yangi kurs boshlandi", "Aksiya! 20% chegirma", "Mijoz fikri", "Maslahat"]),
                url=f"https://example.com/{self.external_id}/{i}",
                published_at=self.now() - timedelta(days=i * 1.5, hours=r.randint(0, 6)),
                duration_sec=30 if t in (MediaType.REEL, MediaType.SHORT, MediaType.VIDEO) else None,
                hashtags=["#demo"]))
        return out

    def fetch_posts(self, since, cursor=None) -> Page:
        return Page([p for p in self._posts() if p.published_at >= since])

    def fetch_post_metrics(self, external_ids):
        out = []
        for eid in external_ids:
            r = _rng(eid, self.now().strftime("%Y%m%d"))
            views = r.randint(200, 6000)
            out.append(PostMetrics(eid, self.now(), views=views, likes=int(views * r.uniform(.02, .12)),
                                   comments=r.randint(0, 40), shares=r.randint(0, 25), saves=r.randint(0, 60),
                                   reach=int(views * .8), watch_time_sec=views * 12.0, avg_view_duration_sec=14.0))
        return out

    def fetch_comments(self, post_external_id, since=None) -> Page:
        r = _rng(post_external_id)
        texts = ["Zo'r ekan!", "Narxi qancha?", "Juda yomon xizmat, hafta o'tdi javob yo'q", "Qayerda joylashgansiz?", "Rahmat"]
        return Page([CommentData(f"{post_external_id}-c{i}", post_external_id, f"user{i}", r.choice(texts),
                                 self.now() - timedelta(hours=i)) for i in range(4)])

    def fetch_stories(self):
        if self.platform != Platform.INSTAGRAM:
            return []
        return [PostData(f"{self.external_id}-s1", MediaType.STORY, None, None, self.now() - timedelta(hours=3))]

    def fetch_story_metrics(self, external_ids):
        return [PostMetrics(e, self.now(), views=_rng(e, self.now().hour).randint(100, 900),
                            reach=300, extra={"replies": 2.0}) for e in external_ids]

    def refresh_credentials(self):
        return Credentials({"token": "fake-refreshed"}, self.now() + timedelta(days=60))

    def dry_run(self, req: PublishRequest) -> DryRunReport:
        probs = []
        if not req.text and not req.media_paths:
            probs.append(RuleProblem("connector.empty", "block", "Matn ham, media ham yo'q."))
        return DryRunReport(not probs, probs)

    def publish(self, req: PublishRequest) -> PublishResult:
        PUBLISH_CALLS.append(req.idempotency_key)
        if req.idempotency_key in PUBLISHED:
            return PUBLISHED[req.idempotency_key]
        if FAIL_NEXT_PUBLISH:
            raise FAIL_NEXT_PUBLISH.pop(0)
        res = PublishResult(f"{self.external_id}-pub{len(PUBLISHED) + 1}",
                            f"https://example.com/{self.external_id}/pub{len(PUBLISHED) + 1}", self.now())
        PUBLISHED[req.idempotency_key] = res
        return res

    def delete_published(self, external_id: str) -> None:
        DELETED.append(external_id)


def reset():
    PUBLISHED.clear(); PUBLISH_CALLS.clear(); FAIL_NEXT_PUBLISH.clear(); DELETED.clear()
