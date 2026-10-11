import pytest

from apps.ai_router.langcheck import check_uz
from apps.ai_router.models import AIKey
from apps.ai_router.providers import FakeAIProvider
from apps.ai_router.router import AIRouter, AIUnavailable
from apps.ai_router.types import AIRequest, TaskType
from apps.connections.base import AuthError, RateLimitError
from apps.core.settings_store import set_setting

UZ = "Bizning yangi kursimiz boshlandi va siz uchun juda katta chegirma bor. Ro'yxatdan o'tish uchun bizga murojaat qiling."


def mk(**p):
    return AIRouter(providers=p, use_fakes=False)


def key(provider, alias="k1"):
    k = AIKey(provider=provider, alias=alias)
    k.set_secret("secret-" + alias)
    k.save()
    return k


def test_lang_checks():
    assert check_uz(UZ).ok
    assert not check_uz("Это текст на русском языке, который не является узбекским совсем и не должен проходить проверку.").ok
    assert not check_uz("This is a long english sentence that should definitely not pass the uzbek language check at all.").ok


def test_failover_to_next_key_then_other_provider(admin):
    set_setting("ai.primary", "openai", user=admin)
    k1, k2 = key("openai", "a"), key("openai", "b")
    key("claude")
    o = FakeAIProvider("openai", [RateLimitError("429"), RateLimitError("429")])
    c = FakeAIProvider("claude", [UZ])
    res = mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "salom", cache_ttl_sec=0))
    assert res.provider == "claude" and o.calls == 2
    k1.refresh_from_db()
    assert k1.cooldown_until is not None


def test_primary_choice_and_task_override(admin):
    key("openai"); key("claude")
    set_setting("ai.primary", "claude", user=admin)
    o, c = FakeAIProvider("openai", [UZ]), FakeAIProvider("claude", [UZ])
    assert mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "a", cache_ttl_sec=0)).provider == "claude"
    set_setting("ai.task.long_uz", "openai", user=admin)
    assert mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "b", cache_ttl_sec=0)).provider == "openai"


def test_fallback_none_does_not_switch(admin):
    key("openai"); key("claude")
    set_setting("ai.primary", "openai", user=admin)
    set_setting("ai.fallback", "none", user=admin)
    o, c = FakeAIProvider("openai", [RateLimitError("429")]), FakeAIProvider("claude", [UZ])
    with pytest.raises(AIUnavailable):
        mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert c.calls == 0


def test_only_providers_with_keys_are_used(admin):
    key("claude")
    set_setting("ai.primary", "openai", user=admin)
    o, c = FakeAIProvider("openai", [UZ]), FakeAIProvider("claude", [UZ])
    res = mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert res.provider == "claude" and o.calls == 0


def test_stt_always_openai(admin):
    key("openai"); key("claude")
    set_setting("ai.primary", "claude", user=admin)
    r = mk(openai=FakeAIProvider("openai", ["matn"]), claude=FakeAIProvider("claude", ["x"]))
    assert [p for p, _ in r._routes(AIRequest(TaskType.STT, "", cache_ttl_sec=0))] == ["openai"]


def test_cooldown_key_skipped(admin):
    key("openai")
    set_setting("ai.fallback", "none", user=admin)
    o = FakeAIProvider("openai", [AuthError("bad key")])
    with pytest.raises(AIUnavailable):
        mk(openai=o).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    o2 = FakeAIProvider("openai", [UZ])
    with pytest.raises(AIUnavailable):  # kalit sovitishda
        mk(openai=o2).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert o2.calls == 0


def test_bad_language_resends_to_next_route(admin):
    key("openai"); key("claude")
    set_setting("ai.primary", "openai", user=admin)
    o = FakeAIProvider("openai", ["This is a long english answer that is definitely not uzbek and should be resent to another model."])
    c = FakeAIProvider("claude", [UZ])
    res = mk(openai=o, claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert res.provider == "claude" and res.lang_check.ok


def test_cache_hit_no_second_call(admin):
    key("openai")
    o = FakeAIProvider("openai", [UZ, UZ])
    r = mk(openai=o)
    r.run(AIRequest(TaskType.LONG_UZ, "same", cache_ttl_sec=3600))
    res = r.run(AIRequest(TaskType.LONG_UZ, "same", cache_ttl_sec=3600))
    assert res.from_cache and o.calls == 1


def test_json_schema_and_invalid_json_falls_through(admin):
    key("openai"); key("claude")
    o = FakeAIProvider("openai", ["bu json emas"])
    c = FakeAIProvider("claude", ['```json\n{"a": 1}\n```'])
    res = mk(openai=o, claude=c).run(AIRequest(TaskType.CLASSIFY, "x", response_schema={"json": True}, cache_ttl_sec=0, require_lang=None))
    assert res.data == {"a": 1} and res.provider == "claude"


def test_secrets_scrubbed_from_prompt(admin):
    key("openai")
    seen = []
    class Spy(FakeAIProvider):
        def call(self, req, k, model, system):
            seen.append(req.prompt)
            return super().call(req, k, model, system)
    res = mk(openai=Spy("openai", [UZ])).run(AIRequest(TaskType.LONG_UZ, "token=abcdef1234567890SECRET shu", cache_ttl_sec=0))
    assert "abcdef1234567890SECRET" not in seen[0]


def test_brand_prompt_injected(admin, biz):
    from apps.businesses.services import approve_brand, save_brand_version
    approve_brand(save_brand_version(biz, "BREND: samimiy ohang", user=admin), admin)
    key("openai")
    seen = []
    class Spy(FakeAIProvider):
        def call(self, req, k, model, system):
            seen.append(system)
            return super().call(req, k, model, system)
    mk(openai=Spy("openai", [UZ])).run(AIRequest(TaskType.LONG_UZ, "x", business_id=biz.pk, cache_ttl_sec=0))
    assert "BREND: samimiy ohang" in seen[0]
