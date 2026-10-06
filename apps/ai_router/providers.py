"""AI provayderlar: Gemini, Groq (chat + Whisper), OpenRouter, Claude, Fake. Hammasi REST (SDK kerak emas)."""
from __future__ import annotations

import base64
import json
import re

import requests

from apps.connections.base import AuthError, PlatformError, RateLimitError, TransientError
from apps.connections.http import raise_for_status
from apps.core.logging_utils import scrub

from .types import AIRequest, RawAIResponse, TaskType


class _Base:
    name = ""

    def supports(self, task: TaskType) -> bool:
        return task != TaskType.STT

    def _post(self, url, **kw):
        try:
            r = requests.post(url, timeout=kw.pop("timeout", 120), **kw)
        except requests.Timeout as e:
            raise TransientError("timeout") from e
        except requests.RequestException as e:
            raise TransientError(scrub(str(e))) from e
        try:
            raise_for_status(r)
        except AuthError:
            raise
        except PlatformError as e:
            low = str(e).lower()
            if any(m in low for m in ("api key not valid", "api_key_invalid", "invalid_api_key", "invalid api key",
                                      "incorrect api key", "authentication_error", "invalid x-api-key", "user not found")):
                raise AuthError(str(e), user_message_uz="AI kaliti noto'g'ri yoki bekor qilingan.") from e
            raise
        return r.json()


class GeminiProvider(_Base):
    name = "gemini"

    def supports(self, task):
        return True  # matn, ko'rish va audio (STT zaxira)

    def call(self, req: AIRequest, key: str, model: str, system: str) -> RawAIResponse:
        prompt = req.prompt or ("Ushbu audioni so'zma-so'z o'zbek tilida (lotin alifbosida) yozib ber. Faqat matnni qaytar."
                                if req.task == TaskType.STT else "")
        parts = [{"text": prompt}]
        for a in req.attachments:
            parts.append({"inlineData": {"mimeType": a.mime, "data": base64.b64encode(a.data).decode()}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.7 if req.task != TaskType.CLASSIFY else 0.1}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if req.response_schema:
            body["generationConfig"]["responseMimeType"] = "application/json"
        j = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       headers={"x-goog-api-key": key}, json=body)
        try:
            text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as e:
            raise TransientError("Gemini bo'sh javob: " + scrub(json.dumps(j)[:200])) from e
        u = j.get("usageMetadata", {})
        return RawAIResponse(text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0))


class _OpenAICompat(_Base):
    url = ""
    extra_headers: dict = {}

    def call(self, req, key, model, system):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": req.prompt}]
        body = {"model": model, "messages": msgs, "temperature": 0.7 if req.task != TaskType.CLASSIFY else 0.1}
        if req.response_schema:
            body["response_format"] = {"type": "json_object"}
        j = self._post(self.url, headers={"Authorization": f"Bearer {key}", **self.extra_headers}, json=body)
        if "error" in j and "choices" not in j:
            msg = str(j["error"])
            if "rate" in msg.lower() or "quota" in msg.lower():
                raise RateLimitError(scrub(msg))
            raise TransientError(scrub(msg))
        u = j.get("usage", {})
        return RawAIResponse(j["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


class GroqProvider(_OpenAICompat):
    name = "groq"
    url = "https://api.groq.com/openai/v1/chat/completions"

    def supports(self, task):
        return task != TaskType.VISION

    def transcribe(self, audio: bytes, key: str, model: str, language: str | None, prompt: str | None, filename="audio.mp3") -> RawAIResponse:
        """Whisper (verbose_json): ishonch ko'rsatkichlari bilan. language='uz' majburan beriladi."""
        data = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt[:220]
        j = self._post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                       data=data, files={"file": (filename, audio)}, timeout=300)
        segs = j.get("segments", [])
        if segs:
            avg_lp = sum(s.get("avg_logprob", -1) for s in segs) / len(segs)
            no_sp = sum(s.get("no_speech_prob", 0) for s in segs) / len(segs)
            comp = sum(s.get("compression_ratio", 1) for s in segs) / len(segs)
        else:
            avg_lp, no_sp, comp = -1.0, 0.0, 1.0
        return RawAIResponse(j.get("text", ""), extra={"avg_logprob": avg_lp, "no_speech_prob": no_sp,
                                                       "compression_ratio": comp, "segments": segs, "language": j.get("language")})

    def call(self, req, key, model, system):
        if req.task == TaskType.STT:
            a = req.attachments[0]
            return self.transcribe(a.data, key, model, req.options.get("language", "uz"), req.options.get("prompt"), a.name)
        return super().call(req, key, model, system)


class OpenRouterProvider(_OpenAICompat):
    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"
    extra_headers = {"X-Title": "SMM Platforma"}

    def supports(self, task):
        return task not in (TaskType.STT, TaskType.VISION)


class OpenAIProvider(_OpenAICompat):
    """platform.openai.com — barcha bepul provayderlar ishlamay qolganda zaxira (chat, ko'rish, Whisper STT)."""
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def supports(self, task):
        return True

    def call(self, req, key, model, system):
        if req.task == TaskType.STT:
            a = req.attachments[0]
            data = {"model": model or "whisper-1", "response_format": "verbose_json", "temperature": "0"}
            lang = req.options.get("language", "uz")
            if lang:
                data["language"] = lang
            if req.options.get("prompt"):
                data["prompt"] = req.options["prompt"][:220]
            j = self._post("https://api.openai.com/v1/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                           data=data, files={"file": (a.name or "audio.mp3", a.data)}, timeout=300)
            segs = j.get("segments", [])
            n = max(1, len(segs))
            return RawAIResponse(j.get("text", ""), extra={
                "avg_logprob": sum(x.get("avg_logprob", -0.5) for x in segs) / n if segs else -0.5,
                "no_speech_prob": sum(x.get("no_speech_prob", 0) for x in segs) / n if segs else 0.0,
                "compression_ratio": 1.0, "segments": segs, "language": j.get("language")})
        imgs = [a for a in req.attachments if a.mime.startswith("image/")]
        if not imgs:
            return super().call(req, key, model, system)
        content = [{"type": "text", "text": req.prompt}] + [
            {"type": "image_url", "image_url": {"url": f"data:{a.mime};base64,{base64.b64encode(a.data).decode()}"}} for a in imgs]
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
        body = {"model": model, "messages": msgs, "temperature": 0.7 if req.task != TaskType.CLASSIFY else 0.1}
        if req.response_schema:
            body["response_format"] = {"type": "json_object"}
        j = self._post(self.url, headers={"Authorization": f"Bearer {key}"}, json=body)
        u = j.get("usage", {})
        return RawAIResponse(j["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


class ClaudeProvider(_Base):
    name = "claude"

    def supports(self, task):
        return task != TaskType.STT

    def call(self, req, key, model, system):
        content = []
        for a in req.attachments:
            if a.mime.startswith("image/"):
                content.append({"type": "image", "source": {"type": "base64", "media_type": a.mime,
                                                             "data": base64.b64encode(a.data).decode()}})
        content.append({"type": "text", "text": req.prompt})
        body = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": content}]}
        if system:
            body["system"] = system
        j = self._post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json=body)
        u = j.get("usage", {})
        return RawAIResponse("".join(b.get("text", "") for b in j.get("content", [])),
                             u.get("input_tokens", 0), u.get("output_tokens", 0))


class FakeAIProvider(_Base):
    """Kalitsiz demo/test. `script` — keyingi javoblar yoki istisnolar."""
    name = "fake"

    def __init__(self, name="fake", script=None):
        self.name = name
        self.script = list(script or [])
        self.calls = 0

    def supports(self, task):
        return True

    def call(self, req, key, model, system):
        self.calls += 1
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return RawAIResponse(item, 10, 10)
        if req.response_schema:
            return RawAIResponse(json.dumps({"ok": True, "items": []}), 5, 5)
        if req.task == TaskType.STT:
            return RawAIResponse("Assalomu alaykum, bizning yangi kursimiz boshlandi, ro'yxatdan o'ting.", extra={"avg_logprob": -0.3, "no_speech_prob": 0.01})
        return RawAIResponse("Bu bizning yangi kurslarimiz haqida qisqa va tushunarli matn. Ro'yxatdan o'tish uchun bizga murojaat qiling.", 20, 30)


def build_registry() -> dict:
    return {p.name: p for p in (GeminiProvider(), GroqProvider(), OpenRouterProvider(), ClaudeProvider())}


class LocalWhisperProvider(_Base):
    """Lokal faster-whisper (ixtiyoriy kutubxona). GTX 1660 Super (6 GB): small/medium int8_float16."""
    name = "local_whisper"
    _model = None

    def supports(self, task):
        return task == TaskType.STT

    def call(self, req, key, model, system):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise PlatformError("faster-whisper o'rnatilmagan") from e
        import os
        import tempfile

        from apps.core.settings_store import get_setting
        size = get_setting("media.local_whisper_model", "small")
        if LocalWhisperProvider._model is None:
            for dev, ct in (("cuda", "int8_float16"), ("cpu", "int8")):
                try:
                    LocalWhisperProvider._model = WhisperModel(size, device=dev, compute_type=ct)
                    break
                except Exception:  # noqa: BLE001
                    continue
        if LocalWhisperProvider._model is None:
            raise TransientError("Whisper modelini yuklab bo'lmadi")
        a = req.attachments[0]
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(a.data)
            p = f.name
        try:
            segs, info = LocalWhisperProvider._model.transcribe(p, language="uz", initial_prompt=req.options.get("prompt"),
                                                                vad_filter=True, beam_size=5, temperature=0.0)
            segs = list(segs)
        finally:
            os.unlink(p)
        n = max(1, len(segs))
        return RawAIResponse(" ".join(s.text.strip() for s in segs),
                             extra={"avg_logprob": sum(s.avg_logprob for s in segs) / n,
                                    "no_speech_prob": sum(s.no_speech_prob for s in segs) / n, "compression_ratio": 1.0})


def build_registry() -> dict:  # noqa: F811 — mahalliy whisper qo'shilgan
    return {p.name: p for p in (GeminiProvider(), GroqProvider(), OpenRouterProvider(), ClaudeProvider(), OpenAIProvider(), LocalWhisperProvider())}


# ---------------- Kalitni tekshirish va model avto-aniqlash ----------------
KEY_HINTS = {
    "gemini": ("AIza", "Gemini kaliti «AIza…» bilan boshlanadi (aistudio.google.com/apikey)."),
    "groq": ("gsk_", "Groq kaliti «gsk_…» bilan boshlanadi (console.groq.com/keys). «xai-…» — bu Groq emas, xAI Grok kaliti."),
    "openrouter": ("sk-or-", "OpenRouter kaliti «sk-or-…» bilan boshlanadi (openrouter.ai/keys)."),
    "openai": ("sk-", "OpenAI kaliti «sk-…» bilan boshlanadi (platform.openai.com/api-keys)."),
    "claude": ("sk-ant-", "Claude kaliti «sk-ant-…» bilan boshlanadi (console.anthropic.com)."),
}


def key_format_problem(provider: str, key: str) -> str | None:
    h = KEY_HINTS.get(provider)
    if h and not key.startswith(h[0]):
        return f"Kalit formati mos emas. {h[1]}"
    return None


def _get(url, headers=None, params=None):
    return requests.get(url, headers=headers or {}, params=params or {}, timeout=15)


def validate_key(provider: str, key: str) -> tuple[bool | None, str]:
    """(True, ok) | (False, sabab) — kalit yaroqsiz | (None, sabab) — tarmoq xatosi, aniqlab bo'lmadi."""
    try:
        if provider == "gemini":
            r = _get("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key}, {"pageSize": 1})
        elif provider == "groq":
            r = _get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
        elif provider == "openrouter":
            r = _get("https://openrouter.ai/api/v1/auth/key", {"Authorization": f"Bearer {key}"})
        elif provider == "openai":
            r = _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
        elif provider == "claude":
            r = _get("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"})
        else:
            return None, "Noma'lum provayder"
    except requests.RequestException as e:
        return None, f"Tarmoq xatosi: {scrub(str(e))[:120]}"
    if r.status_code == 200:
        return True, "Kalit ishlaydi."
    if r.status_code in (400, 401, 403):
        return False, f"Provayder kalitni qabul qilmadi ({r.status_code}). Kalitni to'g'ri nusxalaganingizni tekshiring."
    if r.status_code == 429:
        return True, "Kalit to'g'ri (hozir limit to'lgan)."
    return None, f"Provayder javobi: {r.status_code}"


def _ver(name: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", name)[:3]) or (0,)


def discover_model(provider: str, key: str) -> str | None:
    """Model eskirib 404 bersa — provayderning joriy ro'yxatidan mosini tanlaydi."""
    try:
        if provider == "gemini":
            r = _get("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key}, {"pageSize": 200})
            if r.status_code != 200:
                return None
            names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", []) and m["name"].split("/", 1)[-1].startswith("gemini")]
            bad = ("lite", "image", "tts", "live", "exp", "preview", "thinking", "embedding", "vision", "audio", "robotics", "computer", "customtools", "pro")
            flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]
            if flash:
                return max(flash, key=lambda n: (_ver(n), -len(n)))
            alt = [n for n in names if "flash" in n]
            return max(alt, key=_ver) if alt else (names[0] if names else None)
        if provider == "openai":
            r = _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return None
            ids = [m["id"] for m in r.json().get("data", [])]
            for pref in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini", "gpt-4o"):
                c = sorted(i for i in ids if i.startswith(pref) and not any(b in i for b in ("audio", "realtime", "transcribe", "tts", "search", "preview")))
                if c:
                    return c[0] if pref in ids and pref in c else c[0]
            return None
        if provider == "groq":
            r = _get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return None
            ids = [m["id"] for m in r.json().get("data", []) if m.get("active", True)]
            bad = ("whisper", "guard", "tts", "playai", "orpheus", "distil", "compound", "safeguard")
            chat = [i for i in ids if not any(b in i for b in bad)]
            for pref in ("llama-3.3-70b", "llama-3.1-70b", "70b", "llama"):
                c = [i for i in chat if pref in i]
                if c:
                    return max(c, key=_ver)
            return chat[0] if chat else None
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None
