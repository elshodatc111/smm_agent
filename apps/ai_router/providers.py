"""AI provayderlar: OpenAI (chat, ko'rish, Whisper) va Claude (Anthropic). Hammasi REST (SDK kerak emas)."""
from __future__ import annotations

import base64
import json
import re

import requests

from apps.connections.base import AuthError, NotFoundError, PlatformError, RateLimitError, TransientError
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


class OpenAIProvider(_OpenAICompat):
    """platform.openai.com — chat, ko'rish va Whisper (ovozdan matn)."""
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
    return {p.name: p for p in (OpenAIProvider(), ClaudeProvider())}


# ---------------- Kalitni tekshirish va model avto-aniqlash ----------------
KEY_HINTS = {
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
        if provider == "openai":
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
        if provider == "openai":
            r = _get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return None
            ids = [m["id"] for m in r.json().get("data", [])]
            for pref in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-5-mini", "gpt-4o"):
                c = sorted(i for i in ids if i.startswith(pref) and not any(b in i for b in ("audio", "realtime", "transcribe", "tts", "search", "preview")))
                if c:
                    return c[0]
            return None
        if provider == "claude":
            r = _get("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"})
            if r.status_code != 200:
                return None
            ids = [m["id"] for m in r.json().get("data", [])]
            sonnet = [i for i in ids if "sonnet" in i]
            return max(sonnet, key=_ver) if sonnet else (ids[0] if ids else None)
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None
