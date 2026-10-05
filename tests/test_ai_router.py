import pytest

from apps.ai_router.langcheck import check_uz
from apps.ai_router.models import AIKey, AIUsageLog
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


def test_failover_to_next_key_then_provider(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False], ["openrouter", False]]}, user=admin)
    k1, k2 = key("gemini", "a"), key("gemini", "b")
    key("openrouter")
    g = FakeAIProvider("gemini", [RateLimitError("429"), RateLimitError("429")])
    o = FakeAIProvider("openrouter", [UZ])
    res = mk(gemini=g, openrouter=o).run(AIRequest(TaskType.LONG_UZ, "salom", cache_ttl_sec=0))
    assert res.provider == "openrouter" and g.calls == 2
    k1.refresh_from_db()
    assert k1.cooldown_until is not None


def test_cooldown_key_skipped(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False]]}, user=admin)
    k = key("gemini")
    g = FakeAIProvider("gemini", [AuthError("bad key")])
    with pytest.raises(AIUnavailable):
        mk(gemini=g).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    g2 = FakeAIProvider("gemini", [UZ])
    with pytest.raises(AIUnavailable):  # kalit sovitishda
        mk(gemini=g2).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert g2.calls == 0


def test_claude_never_called_when_disabled(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False], ["claude", True]]}, user=admin)
    key("gemini"); key("claude")
    g = FakeAIProvider("gemini", [RateLimitError("429")])
    c = FakeAIProvider("claude", [UZ])
    with pytest.raises(AIUnavailable):
        mk(gemini=g, claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert c.calls == 0


def test_claude_used_when_enabled_with_budget(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False], ["claude", True]]}, user=admin)
    set_setting("ai.paid.enabled", True, user=admin)
    set_setting("ai.paid.monthly_budget_usd", 5, user=admin)
    key("gemini"); key("claude")
    g = FakeAIProvider("gemini", [RateLimitError("429")])
    c = FakeAIProvider("claude", [UZ])
    res = mk(gemini=g, claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert res.provider == "claude" and c.calls == 1


def test_paid_only_complex_policy(admin):
    set_setting("ai.routes", {"classify": [["groq", False], ["claude", True]]}, user=admin)
    set_setting("ai.paid.enabled", True, user=admin)
    set_setting("ai.paid.monthly_budget_usd", 5, user=admin)
    set_setting("ai.paid.policy", "only_complex", user=admin)
    key("groq"); key("claude")
    g = FakeAIProvider("groq", [RateLimitError("x")])
    c = FakeAIProvider("claude", ["{}"])
    with pytest.raises(AIUnavailable):
        mk(groq=g, claude=c).run(AIRequest(TaskType.CLASSIFY, "x", cache_ttl_sec=0, require_lang=None))
    assert c.calls == 0


def test_budget_exhausted_blocks_paid(admin):
    set_setting("ai.routes", {"long_uz": [["claude", True]]}, user=admin)
    set_setting("ai.paid.enabled", True, user=admin)
    set_setting("ai.paid.monthly_budget_usd", 1, user=admin)
    key("claude")
    AIUsageLog.objects.create(provider="claude", cost_usd=2)
    c = FakeAIProvider("claude", [UZ])
    with pytest.raises(AIUnavailable):
        mk(claude=c).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert c.calls == 0


def test_bad_language_resends_to_next_route(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False], ["openrouter", False]]}, user=admin)
    key("gemini"); key("openrouter")
    g = FakeAIProvider("gemini", ["This is a long english answer that is definitely not uzbek and should be resent to another model."])
    o = FakeAIProvider("openrouter", [UZ])
    res = mk(gemini=g, openrouter=o).run(AIRequest(TaskType.LONG_UZ, "x", cache_ttl_sec=0))
    assert res.provider == "openrouter" and res.lang_check.ok


def test_cache_hit_no_second_call(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False]]}, user=admin)
    key("gemini")
    g = FakeAIProvider("gemini", [UZ, UZ])
    r = mk(gemini=g)
    r.run(AIRequest(TaskType.LONG_UZ, "same", cache_ttl_sec=3600))
    res = r.run(AIRequest(TaskType.LONG_UZ, "same", cache_ttl_sec=3600))
    assert res.from_cache and g.calls == 1


def test_json_schema_and_invalid_json_falls_through(admin):
    set_setting("ai.routes", {"classify": [["groq", False], ["gemini", False]]}, user=admin)
    key("groq"); key("gemini")
    g = FakeAIProvider("groq", ["bu json emas"])
    m = FakeAIProvider("gemini", ['```json\n{"a": 1}\n```'])
    res = mk(groq=g, gemini=m).run(AIRequest(TaskType.CLASSIFY, "x", response_schema={"json": True}, cache_ttl_sec=0, require_lang=None))
    assert res.data == {"a": 1} and res.provider == "gemini"


def test_secrets_scrubbed_from_prompt(admin):
    set_setting("ai.routes", {"long_uz": [["gemini", False]]}, user=admin)
    key("gemini")
    seen = []
    class Spy(FakeAIProvider):
        def call(self, req, k, model, system):
            seen.append(req.prompt)
            return super().call(req, k, model, system)
    res = mk(gemini=Spy("gemini", [UZ])).run(AIRequest(TaskType.LONG_UZ, "token=abcdef1234567890SECRET shu", cache_ttl_sec=0))
    assert "abcdef1234567890SECRET" not in seen[0]


def test_brand_prompt_injected(admin, biz):
    from apps.businesses.services import approve_brand, save_brand_version
    approve_brand(save_brand_version(biz, "BREND: samimiy ohang", user=admin), admin)
    set_setting("ai.routes", {"long_uz": [["gemini", False]]}, user=admin)
    key("gemini")
    seen = []
    class Spy(FakeAIProvider):
        def call(self, req, k, model, system):
            seen.append(system)
            return super().call(req, k, model, system)
    mk(gemini=Spy("gemini", [UZ])).run(AIRequest(TaskType.LONG_UZ, "x", business_id=biz.pk, cache_ttl_sec=0))
    assert "BREND: samimiy ohang" in seen[0]
