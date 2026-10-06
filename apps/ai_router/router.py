"""AI Router (CONTRACTS §4): vazifa -> ketma-ketlik, kalit aylantirish, cooldown, kesh, pullik rejim himoyasi."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.connections.base import (AuthError, NotFoundError, PlatformError, QuotaExceededError, RateLimitError, TransientError)
from apps.core.audit import audit
from apps.core.notify import notify
from apps.core.settings_store import get_setting

from .langcheck import check_uz, scrub_prompt
from .models import AICache, AIGeneration, AIKey, AIUsageLog
from .providers import FakeAIProvider, build_registry, discover_model
from .types import COMPLEX_TASKS, AIRequest, AIResult, LangCheck, TaskType

log = logging.getLogger(__name__)
COOLDOWNS = [60, 300, 1800, 7200]
PRICES = {"claude": (Decimal("3"), Decimal("15")), "openai": (Decimal("0.15"), Decimal("0.60"))}  # USD / 1M token


class AIUnavailable(Exception):
    def __init__(self, msg="", user_message_uz=None):
        super().__init__(msg)
        self.user_message_uz = user_message_uz


def _friendly(err) -> str:
    low = str(err).lower()
    if not err:
        return ("AI kaliti kiritilmagan. Sozlamalar → AI router bo'limida Gemini yoki Groq kalitini qo'shing.")
    if isinstance(err, AuthError) or "api key" in low or "invalid_api_key" in low:
        return "AI kaliti noto'g'ri yoki bekor qilingan. Sozlamalar → AI router → «Tekshirish» tugmasi bilan tekshiring yoki yangi kalit qo'shing."
    if isinstance(err, (RateLimitError, QuotaExceededError)):
        return "AI limiti vaqtincha tugadi. Birozdan keyin urinib ko'ring yoki yana bitta kalit qo'shing."
    return "AI hozir javob bermadi: " + str(err).replace("\n", " ")[:160]


def _json_from(text: str):
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, j = t.find("{"), t.rfind("}")
        if i != -1 and j > i:
            return json.loads(t[i:j + 1])
        raise


class AIRouter:
    def __init__(self, providers: dict | None = None, use_fakes: bool | None = None):
        from django.conf import settings
        self.fake = settings.USE_FAKES if use_fakes is None else use_fakes
        self.providers = providers if providers is not None else (
            {n: FakeAIProvider(n) for n in ("gemini", "groq", "openrouter", "claude", "local_whisper")} if self.fake else build_registry())

    # ---- yo'nalish ----
    def _routes(self, req: AIRequest) -> list[tuple[str, bool]]:
        mode = get_setting("ai.mode", "free_first")
        if mode == "openai_only":      # faqat OpenAI Platform (bepul kalitlar va Claude ishlatilmaydi)
            return [("openai", False)] if self._openai_ok(force=True) else []
        routes = [tuple(r) for r in (get_setting("ai.routes", {}) or {}).get(str(req.task), [])]
        paid_on = bool(get_setting("ai.paid.enabled", False))
        policy = get_setting("ai.paid.policy", "only_when_free_exhausted")
        out = []
        for prov, paid in routes:
            if paid:
                if not paid_on or self._budget_exceeded():
                    continue
                if policy == "only_complex" and req.task not in COMPLEX_TASKS:
                    continue
            out.append((prov, bool(paid)))
        if paid_on and policy == "always":
            out.sort(key=lambda r: not r[1])
        # OpenAI zaxirasi: kaliti bo'lsa va byudjet tugamagan bo'lsa — eng oxirgi urinish sifatida avtomatik qo'shiladi
        if mode == "openai_first" and self._openai_ok(force=True):
            out = [r for r in out if r[0] != "openai"]
            out.insert(0, ("openai", False))
        elif "openai" not in [r[0] for r in out] and self._openai_ok():
            out.append(("openai", False))
        return out

    def _openai_ok(self, force: bool = False) -> bool:
        if self.fake:
            return force
        if not force and not get_setting("ai.openai.fallback", True):
            return False
        if not AIKey.objects.filter(provider="openai", enabled=True).exists():
            return False
        budget = Decimal(str(get_setting("ai.openai.monthly_budget_usd", 10) or 0))
        if budget <= 0:
            return True
        start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent = AIUsageLog.objects.filter(at__gte=start, provider="openai").aggregate(s=Sum("cost_usd"))["s"] or Decimal(0)
        return spent < budget

    def _budget_exceeded(self) -> bool:
        budget = Decimal(str(get_setting("ai.paid.monthly_budget_usd", 0) or 0))
        start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent = AIUsageLog.objects.filter(at__gte=start).aggregate(s=Sum("cost_usd"))["s"] or Decimal(0)
        return budget <= 0 or spent >= budget

    def _keys(self, provider: str, force: bool = False) -> list[AIKey]:
        if self.fake:
            return [AIKey(provider=provider, alias="fake", key_enc="")]
        now = timezone.now()
        qs = AIKey.objects.filter(provider=provider, enabled=True)
        if not force:
            qs = qs.exclude(cooldown_until__gt=now)
        else:   # oxirgi urinish: faqat vaqtinchalik xatodan sovigan kalitlar (noto'g'ri kalit emas)
            qs = qs.exclude(last_error__startswith="[auth]")
        keys = list(qs.order_by("last_ok_at", "id"))
        lim = (get_setting("ai.limits", {}) or {}).get(provider, {})

        def near_limit(k: AIKey) -> bool:
            rpm = k.rpm_limit or lim.get("rpm")
            rpd = k.rpd_limit or lim.get("rpd")
            q = AIUsageLog.objects.filter(provider=provider, key_alias=k.alias)
            if rpm and q.filter(at__gte=now - timedelta(minutes=1)).count() >= 0.9 * rpm:
                return True
            return bool(rpd and q.filter(at__gte=now - timedelta(days=1)).count() >= 0.9 * rpd)
        keys.sort(key=near_limit)  # limitga yaqinlar oxirga
        return keys

    # ---- kesh ----
    def _cache_key(self, req: AIRequest, system: str, model_family: str) -> str:
        att = hashlib.sha256(b"".join(a.data for a in req.attachments)).hexdigest() if req.attachments else ""
        raw = "|".join([str(req.task), model_family, system, req.prompt, att, json.dumps(req.options, sort_keys=True)])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _system(self, req: AIRequest) -> tuple[str, int | None]:
        parts, bv = [], None
        if req.business_id:
            from apps.businesses.models import Business
            b = Business.objects.filter(pk=req.business_id).first()
            bp = b.active_brand if b else None
            if bp:
                parts.append("BREND XOTIRASI:\n" + bp.content)
                bv = bp.version
            if b:
                parts.append(f"BIZNES: {b.name}; faoliyat: {b.industry}; hudud: {b.region}; maqsad: {b.get_main_goal_display()}")
        if req.system_extra:
            parts.append(req.system_extra)
        if req.require_lang == "uz":
            parts.append("Javobni o'zbek tilida (lotin alifbosida), sodda va tushunarli yoz. Narx, chegirma, muddat, telefon "
                         "va manzilni FAQAT yuqoridagi biznes ma'lumotidan ol; o'ylab topma.")
        return "\n\n".join(parts), bv

    # ---- asosiy ----
    def run(self, req: AIRequest, user=None) -> AIResult:
        try:
            return self._run_once(req, user, False)
        except AIUnavailable as e:
            if self.fake or getattr(e, "attempted", True):
                raise
            return self._run_once(req, user, True)   # barcha kalit «sovishda» edi — cooldownni e'tiborsiz qoldirib oxirgi urinish

    def _run_once(self, req: AIRequest, user=None, force: bool = False) -> AIResult:
        attempted = False
        prompt, changed = scrub_prompt(req.prompt)
        if changed:
            audit("ai.prompt_scrubbed", user=user, business_id=req.business_id, target=str(req.task))
            req = _replace(req, prompt=prompt)
        system, bv = self._system(req)
        ttl = req.cache_ttl_sec if req.cache_ttl_sec is not None else int(get_setting("ai.cache.default_ttl_sec", 86400))
        ck = self._cache_key(req, system, "any")
        if ttl:
            hit = AICache.objects.filter(key=ck, expires_at__gt=timezone.now()).first()
            if hit:
                r = hit.result
                return AIResult(r["text"], r.get("data"), r["provider"], r["model"], "cache", 0, 0, Decimal(0), True,
                                LangCheck(**r["lang"]) if r.get("lang") else None)
        routes = self._routes(req)
        last_err: Exception | None = None
        best_bad_lang: AIResult | None = None
        models = get_setting("ai.models", {}) or {}
        for idx, (prov, paid) in enumerate(routes):
            p = self.providers.get(prov)
            if p is None or not p.supports(req.task):
                continue
            if paid and get_setting("ai.paid.policy") == "only_when_free_exhausted" and idx == 0 and len(routes) > 1:
                pass
            model = models.get(f"{prov}_stt" if req.task == TaskType.STT else prov, "")
            if prov == "openai" and req.task in COMPLEX_TASKS and get_setting("ai.openai.model_complex", ""):
                model = get_setting("ai.openai.model_complex", "") or model
            for key in self._keys(prov, force=force):
                attempted = True
                t0 = timezone.now()
                try:
                    raw, model = self._invoke(p, prov, req, key, model, system)
                except (RateLimitError, QuotaExceededError) as e:
                    self._key_fail(key, prov, req, e, hard=True)
                    last_err = e
                    continue
                except (TransientError, AuthError, PlatformError) as e:
                    self._key_fail(key, prov, req, e, hard=isinstance(e, AuthError))
                    last_err = e
                    continue
                ms = (timezone.now() - t0).total_seconds() * 1000
                data = None
                if req.response_schema:
                    try:
                        data = _json_from(raw.text)
                    except (json.JSONDecodeError, ValueError):
                        self._key_fail(key, prov, req, TransientError("yaroqsiz JSON"), hard=False, soft=True)
                        last_err = TransientError("yaroqsiz JSON")
                        break  # keyingi provayderga
                cost = self._cost(prov, raw)
                self._key_ok(key, prov, model, req, raw, cost, ms)
                lc = check_uz(raw.text) if (req.require_lang == "uz" and req.task not in (TaskType.CLASSIFY, TaskType.STT) and not req.response_schema) else None
                res = AIResult(raw.text, data, prov, model, key.alias, raw.tokens_in, raw.tokens_out, cost, False, lc, raw.extra)
                if lc and not lc.ok and idx < len(routes) - 1:
                    best_bad_lang = best_bad_lang or res  # yuqoriroq marshrutga qayta yuborish
                    break
                if ttl and not (lc and not lc.ok):
                    AICache.objects.update_or_create(key=ck, defaults={"result": {
                        "text": res.text, "data": res.data, "provider": prov, "model": model,
                        "lang": {"ok": lc.ok, "score": lc.score, "reason": lc.reason} if lc else None},
                        "expires_at": timezone.now() + timedelta(seconds=ttl)})
                return res
        if best_bad_lang:
            return best_bad_lang
        notify("quota.exhausted", "AI xizmati mavjud emas", str(last_err or "marshrut bo'sh")[:300], severity="warn",
               dedupe_key=f"ai-down:{timezone.now():%Y%m%d%H}")
        msg = _friendly(last_err)
        if last_err is None and not attempted and not self.fake and AIKey.objects.filter(enabled=True).exists():
            msg = "AI kalitlari vaqtincha «sovishda» (oldingi xatolar sabab). Sozlamalar → AI router → «Tekshirish» tugmasini bosing yoki bir necha daqiqadan keyin urining."
        exc = AIUnavailable(str(last_err or "Hech bir AI marshruti mavjud emas (kalit kiritilganmi?)"), msg)
        exc.attempted = attempted
        raise exc

    FALLBACK_MODELS = {"gemini": ["gemini-flash-lite-latest"], "groq": ["llama-3.1-8b-instant"]}

    def _invoke(self, p, prov, req, key, model, system):
        """Bitta chaqiruv: eskirgan model -> avto-aniqlash; band (503) -> qayta urinish -> zaxira model."""
        import time
        secret = key.secret() if not self.fake else ""
        try:
            try:
                return p.call(req, secret, model, system), model
            except NotFoundError as nf:
                new_model = None if self.fake else discover_model(prov, secret)
                if not new_model or new_model == model:
                    raise TransientError(f"Model topilmadi ({model}): {nf}") from nf
                log.warning("AI %s: model %s eskirgan, %s ga almashtirildi", prov, model, new_model)
                self._save_model(prov, req, new_model)
                return p.call(req, secret, new_model, system), new_model
        except TransientError as first:
            if self.fake or "json" in str(first).lower():
                raise
            time.sleep(2.5)   # «high demand / 503» odatda bir necha soniyada o'tadi
            try:
                return p.call(req, secret, model, system), model
            except TransientError as second:
                for alt in self.FALLBACK_MODELS.get(prov, []):
                    if alt == model:
                        continue
                    try:
                        log.warning("AI %s: %s band, zaxira model %s sinab ko'riladi", prov, model, alt)
                        return p.call(req, secret, alt, system), alt
                    except TransientError:
                        continue
                raise second

    def _save_model(self, prov: str, req, new_model: str) -> None:
        from apps.core.settings_store import set_setting
        models = dict(get_setting("ai.models", {}) or {})
        models[f"{prov}_stt" if req.task == TaskType.STT else prov] = new_model
        if prov == "gemini":
            models["gemini"] = models["gemini_stt"] = new_model
        set_setting("ai.models", models)

    def _cost(self, prov: str, raw) -> Decimal:
        if prov not in PRICES:
            return Decimal(0)
        pi, po = PRICES[prov]
        return (Decimal(raw.tokens_in) * pi + Decimal(raw.tokens_out) * po) / Decimal(1_000_000)

    def _key_ok(self, key: AIKey, prov, model, req, raw, cost, ms):
        if key.pk:
            key.fail_streak, key.cooldown_until, key.last_ok_at = 0, None, timezone.now()
            key.save(update_fields=["fail_streak", "cooldown_until", "last_ok_at"])
        AIUsageLog.objects.create(provider=prov, model=model, key_alias=key.alias, task=str(req.task),
                                  business_id=req.business_id, tokens_in=raw.tokens_in, tokens_out=raw.tokens_out,
                                  cost_usd=cost, latency_ms=ms)

    def _key_fail(self, key: AIKey, prov, req, err, hard: bool, soft: bool = False):
        if key.pk and not soft:
            key.fail_streak += 1
            sec = COOLDOWNS[min(key.fail_streak - 1, len(COOLDOWNS) - 1)] * (4 if isinstance(err, AuthError) else 1)
            if isinstance(err, TransientError) and not isinstance(err, RateLimitError):
                sec = min(sec, 30)   # vaqtinchalik server xatosi: kalit aybdor emas, uzoq sovitmaymiz
            key.cooldown_until = timezone.now() + timedelta(seconds=max(sec, getattr(err, "retry_after", None) or 0))
            key.last_error = ("[auth] " if isinstance(err, AuthError) else "") + str(err)[:290]
            key.save(update_fields=["fail_streak", "cooldown_until", "last_error"])
        AIUsageLog.objects.create(provider=prov, key_alias=key.alias, task=str(req.task), business_id=req.business_id,
                                  ok=False, error=str(err)[:300])
        log.warning("AI %s/%s xato: %s", prov, key.alias, err)


def _replace(req: AIRequest, **kw) -> AIRequest:
    from dataclasses import replace
    return replace(req, **kw)


def generate(task: TaskType, prompt: str, *, business=None, kind: str = "", user=None, schema: dict | None = None,
             router: AIRouter | None = None, **kw) -> tuple[AIResult, AIGeneration]:
    """Natijani AIGeneration tarixiga yozib qaytaradi."""
    router = router or AIRouter()
    bid = getattr(business, "pk", None)
    req = AIRequest(task=task, prompt=prompt, business_id=bid, response_schema=schema, kind=kind, **kw)
    res = router.run(req, user=user)
    bp = business.active_brand if business else None
    gen = AIGeneration.objects.create(business=business, task=str(task), kind=kind, prompt=prompt[:8000], text=res.text or "",
                                      data=res.data, provider=res.provider, model=res.model,
                                      brand_version=bp.version if bp else None, from_cache=res.from_cache,
                                      lang_ok=res.lang_check.ok if res.lang_check else True, created_by=user)
    return res, gen
