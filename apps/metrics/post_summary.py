"""Post natijasi bo'yicha avtomatik xulosa: raqamlar asosida (AI'siz ham ishlaydi), AI bo'lsa sabab va tavsiyalar bilan boyitiladi."""
from __future__ import annotations

import logging

from apps.core.notify import notify

from .analytics import median_baseline
from .models import Post

log = logging.getLogger(__name__)
WIN = {"24h": "24 soatda", "7d": "7 kunda"}


def _n(v) -> str:
    return "—" if v is None else f"{int(v):,}".replace(",", " ")


def verdict_of(last, base) -> tuple[str, str]:
    """(kod, matn): winner|good|average|weak"""
    if last is None:
        return "none", "ma'lumot yo'q"
    ratio = None
    if last.views and base.get("views"):
        ratio = last.views / base["views"]
    elif last.er and base.get("er"):
        ratio = last.er / base["er"]
    if ratio is None:
        return "average", "taqqoslash uchun yetarli tarix yo'q"
    if ratio >= 1.5:
        return "winner", f"o'rtachadan {ratio:.1f}× yuqori — g'olib post 🏆"
    if ratio >= 1.1:
        return "good", f"o'rtachadan {ratio:.1f}× yuqori ✅"
    if ratio >= 0.8:
        return "average", "o'rtacha natija"
    return "weak", f"o'rtachadan past ({ratio:.1f}×) ⚠"


def build(post: Post, window: str) -> dict:
    last = post.history.order_by("-taken_at").first()
    base = median_baseline(post.business)
    code, vtxt = verdict_of(last, base)
    if last is None:
        return {"code": code, "text": "Hali statistika yig'ilmagan.", "line": ""}
    er = f"{last.er * 100:.1f}%" if last.er is not None else "—"
    line = f"{WIN.get(window, window)}: {_n(last.views)} ko'rish, {_n(last.likes)} layk, {_n(last.comments)} izoh, {_n(last.shares)} ulashish, {_n(last.saves)} saqlash · ER {er}"
    return {"code": code, "line": line, "text": f"{line}. Biznes o'rtachasiga nisbatan: {vtxt}.", "numbers": {
        "views": last.views, "likes": last.likes, "comments": last.comments, "shares": last.shares, "saves": last.saves, "er": last.er,
        "baseline_views": base.get("views"), "baseline_er": base.get("er"), "window": window}}


def run(post_id: int, window: str) -> dict:
    from apps.studio.models import PostInsight
    post = Post.objects.select_related("business", "content_item").get(pk=post_id)
    s = build(post, window)
    if s["code"] == "none":
        return {"skipped": "statistika yo'q"}
    ai_text, data = "", None
    try:
        from apps.studio import services
        ins = services.why_worked(post)
        ai_text, data = ins.text, ins.data
        ins.numbers = {**(ins.numbers or {}), **s.get("numbers", {}), "summary_window": window}
        ins.verdict = s["code"] if s["code"] in ("winner", "average", "weak") else ("winner" if s["code"] == "winner" else "average")
        ins.text = s["text"] + (("\n\n" + ai_text) if ai_text else "")
        ins.save()
    except Exception as e:  # noqa: BLE001 — AI bo'lmasa ham raqamli xulosa saqlanadi
        log.info("post_summary: AI xulosasi o'tkazib yuborildi: %s", str(e)[:160])
        PostInsight.objects.create(post=post, numbers={**s.get("numbers", {}), "summary_window": window}, verdict="winner" if s["code"] == "winner" else ("weak" if s["code"] == "weak" else "average"), text=s["text"], data=None)
    title = (post.content_item.title if post.content_item_id and post.content_item.title else (post.text or "post")[:50])
    notify("post.insight", f"Natija ({WIN.get(window, window)}): {title}", s["text"][:400] + (f"\n💡 {ai_text[:240]}" if ai_text else ""),
           business_id=post.business_id, severity="info" if s["code"] != "weak" else "warn",
           link=f"/kalendar/{post.content_item_id}/" if post.content_item_id else f"/tahlil/post/{post.pk}/", dedupe_key=f"pi:{post.pk}:{window}", dedupe_minutes=60 * 24 * 10)
    return {"verdict": s["code"]}
