"""Mijozga har bir nashr haqida avtomatik Telegram xabari: qaysi post/story/reels qaysi platformaga qachon yuklandi."""
from __future__ import annotations

import logging

from django.utils import timezone

from apps.core.settings_store import get_setting
from apps.core.utils import fmt_dt

from .models import ClientBotUser, ClientNotice

log = logging.getLogger(__name__)

PLAT = {"telegram": "Telegram", "instagram": "Instagram", "youtube": "YouTube"}
FMT = {"text": "Matnli post", "image": "Rasmli post", "video": "Video", "album": "Albom", "reel": "Reels", "short": "Shorts", "story": "Stories", "carousel": "Karusel"}


def _line(t) -> str:
    acc = t.account
    h = acc.handle or acc.name
    return f"• {PLAT.get(acc.platform, acc.platform)} — {acc.name}" + (f" ({h})" if h and h != acc.name else "") + (f"\n   🔗 {t.url}" if t.url and t.item.media_type != "story" else "")


def build_text(item, targets) -> str:
    when = max((t.published_at for t in targets if t.published_at), default=timezone.now())
    fmt = FMT.get(item.media_type, item.media_type)
    head = "✅ Yangi nashr" if len(targets) == 1 else f"✅ Yangi nashr — {len(targets)} ta platformaga"
    body = (item.title or (item.text or "")[:80]).strip()
    excerpt = (item.text or "").strip().replace("\n", " ")
    if excerpt and excerpt != body:
        body += (" — " if body else "") + (excerpt[:140] + ("…" if len(excerpt) > 140 else ""))
    lines = [head, f"🏢 {item.business.name}", f"🧩 Turi: {fmt}", ""]
    lines += [_line(t) for t in targets]
    lines += ["", f"🕒 {fmt_dt(when)} (Toshkent vaqti)"]
    if body:
        lines += ["", f"📝 {body}"]
    if item.media_type == "story":
        lines += ["", "ℹ️ Stories 24 soat ko'rinadi; natijalari keyin hisobotda bo'ladi."]
    return "\n".join(lines)[:3900]


def send_for_target(target_id: int, api=None) -> dict:
    from apps.content.models import ContentTarget
    from .bot import make_api
    if not get_setting("client.publish_notice", True):
        return {"skipped": "o'chirilgan"}
    t = ContentTarget.objects.select_related("item", "item__business", "account").filter(pk=target_id, status="published").first()
    if not t:
        return {"skipped": "nashr topilmadi"}
    if ClientNotice.objects.filter(target_id=t.pk).exists():
        return {"skipped": "yuborilgan"}
    item = t.item
    sibs = [x for x in item.targets.select_related("account", "item").filter(status="published")
            if not ClientNotice.objects.filter(target_id=x.pk).exists()]
    if t not in sibs:
        sibs.append(t)
    users = [u for u in ClientBotUser.objects.filter(active=True) if item.business_id in u.business_ids and "publish_notice" in u.allowed(item.business_id)]
    api = api or make_api()
    sent = 0
    if users and api is not None:
        text = build_text(item, sibs)
        for u in users:
            try:
                api.send(u.tg_user_id, text)
                sent += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Mijozga xabar yuborilmadi (%s): %s", u.tg_user_id, e)
    for x in sibs:
        ClientNotice.objects.get_or_create(target_id=x.pk, defaults={"business_id": item.business_id, "sent_to": sent})
    return {"sent_to": sent, "targets": len(sibs)}
