"""Murojaatlar: operator akkauntlariga mijozlar yozgan xabarlar, AI javob skripti, javoblar jurnali."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.accounts.services import perms
from apps.core import crypto
from apps.core.audit import audit
from apps.inbox import services as svc
from apps.inbox.models import AIReplyLog, Conversation, InboxAccount, Message, ScriptEntry, ScriptGap

from .common import get_obj


def _biz_ids(request, code="inbox.view"):
    b = request.business
    if b and perms.can(request.user, code, b):
        return [b.pk]
    return list(perms.businesses_for(request.user, code).values_list("pk", flat=True))


def _lines(text: str) -> list[str]:
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


# ------------------------------------------------------------------ ro'yxat
@login_required
@require_permission("inbox.view")
def inbox_home(request):
    ids = _biz_ids(request)
    now = timezone.now()
    tab = request.GET.get("tab", "all")
    qs = Conversation.objects.filter(business_id__in=ids, status="open").select_related("account", "business")
    rows = []
    for c in qs.order_by("-last_message_at")[:200]:
        wait = svc.awaiting_message(c)
        join = svc.ai_join_at(c, now) if wait else None
        last = c.messages.order_by("-created_at", "-pk").first()
        state = "human" if c.needs_human else ("waiting" if wait else "answered")
        if tab == "waiting" and state != "waiting":
            continue
        if tab == "human" and state != "human":
            continue
        if tab == "ai" and not c.messages.filter(sender="ai").exists():
            continue
        secs = max(0, int((join - now).total_seconds())) if join and join > now else 0
        mins = secs // 60 if secs >= 60 else 0
        join_ms = int(join.timestamp() * 1000) if join and join > now else 0
        rows.append({"c": c, "last": last, "state": state, "join_in": mins, "join_secs": secs, "join_ms": join_ms, "ai_active": bool(join and join <= now and c.ai_enabled and c.account.auto_reply and not svc.is_hard(c))})
    return render(request, "inbox_home.html", {"title": "Murojaatlar", "rows": rows, "now_ms": int(now.timestamp() * 1000), "tab": tab, "stat": svc.stats(ids),
                                               "can_manage": perms.can(request.user, "inbox.configure", request.business) if request.business else request.user.is_admin,
                                               "no_accounts": not InboxAccount.objects.filter(business_id__in=ids).exists()})


@login_required
def inbox_conv(request, pk):
    c = get_obj(request, Conversation, pk, "inbox.view")
    c.unread = False
    c.save(update_fields=["unread"])
    msgs = list(c.messages.order_by("created_at", "pk"))
    wait = svc.awaiting_message(c)
    join = svc.ai_join_at(c) if wait else None
    return render(request, "inbox_conv.html", {
        "title": str(c), "c": c, "msgs": msgs, "join": join, "now_ms": int(timezone.now().timestamp() * 1000),
        "join_ms": int(join.timestamp() * 1000) if join else 0, "hard": svc.is_hard(c), "waiting": bool(wait), "suggestions": request.session.pop(f"sug{c.pk}", None),
        "can_reply": perms.can(request.user, "inbox.create", c.business), "can_script": perms.can(request.user, "inbox.edit", c.business),
        "logs": c.ai_logs.all()[:5]})


@login_required
@require_POST
def inbox_reply(request, pk):
    c = get_obj(request, Conversation, pk, "inbox.create")
    text = request.POST.get("text", "").strip()
    if not text:
        messages.error(request, "Xabar bo'sh.")
    else:
        svc.queue_outbound(c, text, sender="operator", user=request.user)
        audit("inbox.reply", user=request.user, business_id=c.business_id, target=f"conv:{c.pk}")
        messages.success(request, "Javob yuborish navbatiga qo'yildi (bir necha soniyada ketadi).")
    return redirect("inbox_conv", pk=c.pk)


@login_required
@require_POST
def inbox_suggest(request, pk):
    c = get_obj(request, Conversation, pk, "inbox.create")
    try:
        request.session[f"sug{c.pk}"] = svc.suggest_replies(c, request.user)
    except Exception as e:  # noqa: BLE001
        messages.error(request, getattr(e, "user_message_uz", None) or f"AI xatosi: {e}")
    return redirect("inbox_conv", pk=c.pk)


@login_required
@require_POST
def inbox_conv_action(request, pk, action):
    c = get_obj(request, Conversation, pk, "inbox.create")
    if action == "ai":
        c.ai_enabled = not c.ai_enabled
        c.save(update_fields=["ai_enabled"])
        messages.info(request, "Bu suhbatda AI " + ("yoqildi." if c.ai_enabled else "o'chirildi: faqat operator javob beradi."))
    elif action == "close":
        c.status = "closed"
        c.save(update_fields=["status"])
        messages.info(request, "Suhbat yopildi (mijoz yana yozsa qayta ochiladi).")
        return redirect("inbox_home")
    elif action == "human":
        c.needs_human = False
        c.human_reason = ""
        c.save(update_fields=["needs_human", "human_reason"])
        messages.info(request, "AI yana javob bera oladi.")
    else:
        raise Http404
    return redirect("inbox_conv", pk=c.pk)


@login_required
@require_POST
def inbox_add_script(request, pk, msg_id):
    c = get_obj(request, Conversation, pk, "inbox.edit")
    m = Message.objects.filter(pk=msg_id, conversation=c).first()
    e = svc.add_to_script(c, m, request.user) if m else None
    messages.success(request, "Skriptga qo'shildi: AI endi shu savolga shu javobni beradi.") if e else messages.error(request, "Faqat operatorning javobini skriptga qo'shish mumkin.")
    return redirect("inbox_conv", pk=c.pk)


# ------------------------------------------------------------------ akkauntlar
@login_required
@require_permission("inbox.view")
def inbox_accounts(request):
    ids = _biz_ids(request)
    accs = InboxAccount.objects.filter(business_id__in=ids).select_related("business", "operator")
    from apps.accounts.models import User
    return render(request, "inbox_accounts.html", {"title": "Murojaatlar: akkauntlar", "accs": accs, "can_manage": perms.can(request.user, "inbox.configure", request.business) if request.business else request.user.is_admin,
                                                   "businesses": perms.businesses_for(request.user, "inbox.configure"), "operators": User.objects.filter(is_active=True).order_by("username"),
                                                   "tl": request.session.get("inbox_tl"), "cur": request.business})


@login_required
@require_POST
@require_permission("inbox.configure")
def inbox_account_add(request):
    from django.conf import settings

    from apps.accounts.models import User
    from apps.businesses.models import Business
    from apps.connections import telethon_login as tl
    from apps.connections.base import PlatformError
    st = request.session.get("inbox_tl")
    try:
        if not st:
            b = Business.objects.filter(pk=request.POST.get("business")).first()
            if not b or not perms.can(request.user, "inbox.configure", b) or not perms.has_business(request.user, b.pk):
                raise PermissionError("Bu biznes uchun ruxsat yo'q")
            op = User.objects.filter(pk=request.POST.get("operator")).first() if request.POST.get("operator") else None
            data = {"business": b.pk, "operator": op.pk if op else None, "name": (request.POST.get("name") or "Operator")[:80], "ai_name": (request.POST.get("ai_name") or "").strip()[:40], "phone": request.POST.get("phone", "").strip()}
            if settings.USE_FAKES:
                InboxAccount.objects.create(business=b, operator=op, name=data["name"], ai_name=data["ai_name"], phone=data["phone"], session_enc=crypto.encrypt("fake"), connected_at=timezone.now())
                messages.success(request, "Demo akkaunt qo'shildi.")
                return redirect("inbox_accounts")
            r = tl.send_code(data["phone"])
            request.session["inbox_tl"] = {**r, **data}
            messages.info(request, "Kod Telegram ilovasiga yuborildi.")
        else:
            r = tl.sign_in(st["phone"], st["session"], st["hash"], code=request.POST.get("code", "").strip(), password=request.POST.get("password", ""))
            if r.get("need_password"):
                request.session["inbox_tl"] = {**st, "session": r["session"], "need_password": True}
                messages.info(request, "Ikki bosqichli parol kerak.")
            else:
                b = Business.objects.get(pk=st["business"])
                InboxAccount.objects.create(business=b, operator_id=st.get("operator"), name=st["name"], ai_name=st.get("ai_name", ""), phone=st["phone"], session_enc=crypto.encrypt(r["session"]), connected_at=timezone.now())
                request.session.pop("inbox_tl", None)
                audit("inbox.account_added", user=request.user, business_id=b.pk, target=st["name"])
                messages.success(request, "Akkaunt ulandi. Mijozlar yozgan xabarlar shu yerda ko'rinadi (worker qayta ishga tushganda tinglash boshlanadi).")
    except PlatformError as e:
        messages.error(request, e.user_message_uz or str(e))
    except PermissionError as e:
        messages.error(request, str(e))
    except Exception as e:  # noqa: BLE001
        request.session.pop("inbox_tl", None)
        messages.error(request, f"Kirishda xato: {e}")
    return redirect("inbox_accounts")


@login_required
@require_POST
def inbox_account_cancel(request):
    request.session.pop("inbox_tl", None)
    return redirect("inbox_accounts")


@login_required
@require_POST
def inbox_account_edit(request, pk):
    a = get_obj(request, InboxAccount, pk, "inbox.configure")
    act = request.POST.get("action")
    if act == "auto":
        a.auto_reply = not a.auto_reply
    elif act == "active":
        a.active = not a.active
        if a.active:
            a.last_error, a.cooldown_until = "", None
    elif act == "save":
        a.ai_name = (request.POST.get("ai_name") or "").strip()[:40]
        try:
            a.wait_minutes = min(max(int(request.POST.get("wait_minutes", 15)), 1), 240)
            a.hourly_limit = min(max(int(request.POST.get("hourly_limit", 30)), 1), 200)
            a.ai_delay_seconds = min(max(int(request.POST.get("ai_delay_seconds", 30)), 5), 600)
            a.ai_session_minutes = min(max(int(request.POST.get("ai_session_minutes", 180)), 5), 1440)
        except ValueError:
            messages.error(request, "Son kiriting.")
            return redirect("inbox_accounts")
    elif act == "delete":
        audit("inbox.account_deleted", user=request.user, business_id=a.business_id, target=a.name)
        a.delete()
        messages.success(request, "Akkaunt va uning suhbatlari o'chirildi.")
        return redirect("inbox_accounts")
    else:
        raise Http404
    a.save()
    messages.success(request, "Saqlandi.")
    return redirect("inbox_accounts")


# ------------------------------------------------------------------ skript
@login_required
@require_permission("inbox.view")
def inbox_script(request):
    ids = _biz_ids(request)
    b = request.business
    entries = ScriptEntry.objects.filter(business_id__in=ids).select_related("business")
    gaps = ScriptGap.objects.filter(business_id__in=ids, status="new").select_related("business", "conversation")[:30]
    edit = ScriptEntry.objects.filter(pk=request.GET.get("edit"), business_id__in=ids).first() if request.GET.get("edit") else None
    return render(request, "inbox_script.html", {"title": "Murojaatlar: AI skripti", "entries": entries, "gaps": gaps, "edit": edit, "cur": b,
                                                 "businesses": perms.businesses_for(request.user, "inbox.edit"), "can_edit": perms.can(request.user, "inbox.edit", b) if b else request.user.is_admin,
                                                 "kinds": ScriptEntry.KINDS})


@login_required
@require_POST
def inbox_script_save(request):
    from apps.businesses.models import Business
    pk = request.POST.get("id")
    e = get_obj(request, ScriptEntry, pk, "inbox.edit") if pk else None
    b = e.business if e else Business.objects.filter(pk=request.POST.get("business")).first()
    if not b or not perms.can(request.user, "inbox.edit", b) or not perms.has_business(request.user, b.pk):
        raise Http404
    kind = request.POST.get("kind", "qa")
    title, answer, questions = request.POST.get("title", "").strip(), request.POST.get("answer", "").strip(), request.POST.get("questions", "").strip()
    if not title or (kind != "handoff" and not answer):
        messages.error(request, "Sarlavha va javob to'ldirilishi kerak.")
        return redirect("inbox_script")
    if kind not in dict(ScriptEntry.KINDS):
        kind = "qa"
    if e:
        e.kind, e.title, e.answer, e.questions = kind, title[:160], answer[:3000], questions[:2000]
        e.save()
    else:
        e = ScriptEntry.objects.create(business=b, kind=kind, title=title[:160], answer=answer[:3000], questions=questions[:2000], created_by=request.user)
    audit("inbox.script_save", user=request.user, business_id=b.pk, target=f"script:{e.pk}")
    messages.success(request, "Skript saqlandi.")
    return redirect("inbox_script")


@login_required
@require_POST
def inbox_script_action(request, pk, action):
    e = get_obj(request, ScriptEntry, pk, "inbox.edit")
    if action == "toggle":
        e.active = not e.active
        e.save(update_fields=["active"])
    elif action == "delete":
        e.delete()
        messages.success(request, "O'chirildi.")
    else:
        raise Http404
    return redirect("inbox_script")


@login_required
@require_POST
def inbox_gap_action(request, pk, action):
    g = get_obj(request, ScriptGap, pk, "inbox.edit")
    if action == "ignore":
        g.status = "ignored"
        g.save(update_fields=["status"])
    elif action == "add":
        ans = request.POST.get("answer", "").strip()
        if not ans:
            messages.error(request, "Javobni yozing.")
            return redirect("inbox_script")
        ScriptEntry.objects.create(business=g.business, kind="qa", title=g.question[:80], questions=g.question[:500], answer=ans[:3000], source="learned", created_by=request.user)
        g.status = "added"
        g.save(update_fields=["status"])
        messages.success(request, "Skriptga qo'shildi.")
    else:
        raise Http404
    return redirect("inbox_script")


# ------------------------------------------------------------------ jurnal
@login_required
@require_permission("inbox.view")
def inbox_log(request):
    ids = _biz_ids(request)
    qs = AIReplyLog.objects.filter(business_id__in=ids).select_related("conversation", "business")
    dec = request.GET.get("d", "")
    if dec in dict(AIReplyLog.DECISIONS):
        qs = qs.filter(decision=dec)
    return render(request, "inbox_log.html", {"title": "AI javoblar jurnali", "rows": qs[:200], "dec": dec, "decisions": AIReplyLog.DECISIONS})
