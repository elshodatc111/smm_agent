from datetime import timedelta

import pytest
from django.utils import timezone

from apps.connections.base import Platform, QuotaExceededError
from apps.core.settings_store import set_setting
from apps.providers.base import DataKind, DataRequest, NoProviderAvailable
from apps.providers.impl import FakeProvider
from apps.providers.models import FailoverEvent, ProviderState
from apps.providers.quota import record_usage
from apps.providers.router import ProviderRouter


def req(target="chan"):
    return DataRequest(Platform.YOUTUBE, DataKind.PROFILE, target, cache_max_age_sec=0)


@pytest.fixture
def two(admin):
    yt, sc = FakeProvider("youtube_data_api"), FakeProvider("scrapecreators", unit="credits", cost=1)
    set_setting("providers.priority", {"youtube": ["youtube_data_api", "scrapecreators"]}, user=admin)
    return yt, sc, ProviderRouter({"youtube_data_api": yt, "scrapecreators": sc})


def test_primary_used_first(two):
    yt, sc, r = two
    assert r.fetch(req()).provider == "youtube_data_api" and sc.calls == 0


def test_quota_exceeded_switches_and_cooldown(two):
    yt, sc, r = two
    yt.fail_with = QuotaExceededError("quotaExceeded")
    assert r.fetch(req()).provider == "scrapecreators"
    assert FailoverEvent.objects.filter(from_provider="youtube_data_api", to_provider="scrapecreators").exists()
    yt.fail_with = None
    yt.calls = 0
    assert r.fetch(req("b")).provider == "scrapecreators" and yt.calls == 0  # sovitishda


def test_switch_at_quota_threshold(two):
    yt, sc, r = two
    record_usage("youtube_data_api", units=9500, kind="api")
    assert r.fetch(req()).provider == "scrapecreators"


def test_returns_to_primary_after_cooldown(two):
    yt, sc, r = two
    yt.fail_with = QuotaExceededError("q")
    r.fetch(req())
    yt.fail_with = None
    ProviderState.objects.filter(name="youtube_data_api").update(cooldown_until=timezone.now() - timedelta(minutes=1))
    assert r.fetch(req("c")).provider == "youtube_data_api"


def test_low_credits_back_to_data_api(admin):
    yt, sc = FakeProvider("youtube_data_api"), FakeProvider("scrapecreators", unit="credits")
    set_setting("providers.priority", {"youtube": ["scrapecreators", "youtube_data_api"]}, user=admin)
    ProviderState.objects.create(name="scrapecreators", credits_remaining=5)
    r = ProviderRouter({"youtube_data_api": yt, "scrapecreators": sc})
    assert r.fetch(req()).provider == "youtube_data_api" and sc.calls == 0


def test_both_exhausted_defers_to_pacific_reset(two):
    yt, sc, r = two
    yt.fail_with = QuotaExceededError("q")
    sc.fail_with = QuotaExceededError("q")
    with pytest.raises(NoProviderAvailable) as e:
        r.fetch(req())
    assert e.value.retry_at > timezone.now()


def test_per_run_cap_blocks_expensive(admin):
    sc = FakeProvider("scrapecreators", unit="credits", cost=50)
    set_setting("providers.priority", {"youtube": ["scrapecreators"]}, user=admin)
    with pytest.raises(NoProviderAvailable):
        ProviderRouter({"scrapecreators": sc}).fetch(req())
    assert sc.calls == 0


def test_cache_prevents_second_call(two):
    yt, sc, r = two
    q = DataRequest(Platform.YOUTUBE, DataKind.PROFILE, "x", cache_max_age_sec=3600)
    r.fetch(q)
    assert r.fetch(q).from_cache and yt.calls == 1


def test_credit_accounting_decrements(admin):
    sc = FakeProvider("scrapecreators", unit="credits", cost=2)
    set_setting("providers.priority", {"youtube": ["scrapecreators"]}, user=admin)
    ProviderState.objects.create(name="scrapecreators", credits_remaining=100)
    ProviderRouter({"scrapecreators": sc}).fetch(req())
    assert ProviderState.objects.get(name="scrapecreators").credits_remaining == 98
