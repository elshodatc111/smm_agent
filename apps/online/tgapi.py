"""Telegram Bot API (requests orqali) va testlar uchun soxta (Fake) variant."""
from __future__ import annotations

import json
import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class TgError(Exception):
    def __init__(self, description="", code=0):
        super().__init__(description)
        self.description = description
        self.code = code

    @property
    def blocked(self):
        d = self.description.lower()
        return "blocked" in d or "deactivated" in d or "chat not found" in d or "user is deactivated" in d


def _markup(m):
    return json.dumps(m, ensure_ascii=False) if isinstance(m, (dict, list)) else m


class BotAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def call(self, method, files=None, http_timeout=60, **kw):
        data = {k: (_markup(v) if isinstance(v, (dict, list)) else v) for k, v in kw.items() if v is not None}
        try:
            r = requests.post(f"{self.base}/{method}", data=data, files=files, timeout=http_timeout)
            j = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TgError(f"Tarmoq xatosi: {str(e)[:120]}") from e
        if not j.get("ok"):
            raise TgError(str(j.get("description", "")), int(j.get("error_code", 0)))
        return j["result"]

    # --- asosiy ---
    def get_me(self): return self.call("getMe")
    def get_updates(self, offset, poll=25):
        allowed = ["message", "callback_query", "chat_join_request", "chat_member", "my_chat_member"]
        return self.call("getUpdates", http_timeout=poll + 15, offset=offset, timeout=poll, allowed_updates=allowed)
    def delete_webhook(self): return self.call("deleteWebhook")

    def send(self, chat_id, text, markup=None, parse_mode="HTML", **kw):
        return self.call("sendMessage", chat_id=chat_id, text=text[:4096], reply_markup=markup, parse_mode=parse_mode, disable_web_page_preview=True, **kw)

    def send_media(self, chat_id, kind, media, caption="", markup=None, parse_mode="HTML"):
        """media: file_id (str) yoki (nom, bytes) — yuklanadi."""
        field = "video" if kind == "video" else "photo"
        method = "sendVideo" if kind == "video" else "sendPhoto"
        if isinstance(media, str):
            return self.call(method, chat_id=chat_id, caption=caption[:1024], reply_markup=markup, parse_mode=parse_mode, **{field: media})
        return self.call(method, files={field: media}, chat_id=chat_id, caption=caption[:1024], reply_markup=markup, parse_mode=parse_mode, http_timeout=300)

    def edit_markup(self, chat_id, message_id, markup=None):
        return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=markup or {"inline_keyboard": []})

    def edit_text(self, chat_id, message_id, text, markup=None, parse_mode="HTML"):
        return self.call("editMessageText", chat_id=chat_id, message_id=message_id, text=text[:4096], reply_markup=markup, parse_mode=parse_mode, disable_web_page_preview=True)

    def edit_caption(self, chat_id, message_id, caption, markup=None, parse_mode="HTML"):
        return self.call("editMessageCaption", chat_id=chat_id, message_id=message_id, caption=caption[:1024], reply_markup=markup, parse_mode=parse_mode)

    def answer(self, cb_id, text="", alert=False):
        try:
            return self.call("answerCallbackQuery", callback_query_id=cb_id, text=text[:190], show_alert=alert)
        except TgError:
            return None

    def file_bytes(self, file_id):
        info = self.call("getFile", file_id=file_id)
        r = requests.get(self.base.replace("/bot", "/file/bot") + "/" + info["file_path"], timeout=60)
        return r.content

    # --- guruh nazorati ---
    def create_invite(self, chat_id, name="", expire=None):
        return self.call("createChatInviteLink", chat_id=chat_id, name=name[:32], creates_join_request=True, expire_date=expire)
    def approve_join(self, chat_id, user_id): return self.call("approveChatJoinRequest", chat_id=chat_id, user_id=user_id)
    def decline_join(self, chat_id, user_id): return self.call("declineChatJoinRequest", chat_id=chat_id, user_id=user_id)
    def kick(self, chat_id, user_id):
        self.call("banChatMember", chat_id=chat_id, user_id=user_id)
        try:
            self.call("unbanChatMember", chat_id=chat_id, user_id=user_id, only_if_banned=True)
        except TgError:
            pass
    def get_member(self, chat_id, user_id): return self.call("getChatMember", chat_id=chat_id, user_id=user_id)
    def get_chat(self, chat_id): return self.call("getChat", chat_id=chat_id)
    def user_photos(self, user_id): return self.call("getUserProfilePhotos", user_id=user_id, limit=1)

    # --- bot profili ---
    def set_name(self, name): return self.call("setMyName", name=name)
    def set_description(self, text): return self.call("setMyDescription", description=text)
    def set_about(self, text): return self.call("setMyShortDescription", short_description=text)
    def set_commands(self, cmds, scope=None): return self.call("setMyCommands", commands=cmds, scope=scope)
    def set_menu_button(self): return self.call("setChatMenuButton", menu_button={"type": "commands"})
    def set_photo(self, path):
        with open(path, "rb") as f:
            return self.call("setMyProfilePhoto", files={"photo_file": f}, photo={"type": "static", "photo": "attach://photo_file"})


class FakeBotAPI:
    """Testlar uchun: hamma chaqiruvni yozib boradi."""
    registry: dict = {}

    def __init__(self, token="fake"):
        self.calls, self.sent, self.mid = [], [], 1000
        self.members: dict = {}        # (chat_id, user_id) -> status
        self.fail: dict = {}           # method -> TgError
        self.me = {"id": 999, "username": "fake_bot", "first_name": "Fake Bot"}
        self.chat_rights = {"status": "administrator", "can_restrict_members": True, "can_invite_users": True, "can_post_messages": True, "can_delete_messages": True}

    def _rec(self, _n, **kw):
        self.calls.append((_n, kw))
        if _n in self.fail:
            raise self.fail[_n]

    def _msg(self, chat_id, **kw):
        self.mid += 1
        m = {"message_id": self.mid, "chat": {"id": chat_id}, **kw}
        self.sent.append(m)
        return m

    def call(self, method, **kw): self._rec(method, **kw); return {}
    def get_me(self): self._rec("getMe"); return self.me
    def delete_webhook(self): self._rec("deleteWebhook"); return True
    def send(self, chat_id, text, markup=None, parse_mode="HTML", **kw):
        self._rec("sendMessage", chat_id=chat_id, text=text, markup=markup)
        return self._msg(chat_id, text=text, markup=markup)
    def send_media(self, chat_id, kind, media, caption="", markup=None, parse_mode="HTML"):
        self._rec("sendMedia", chat_id=chat_id, kind=kind, caption=caption, markup=markup)
        fid = media if isinstance(media, str) else f"fid_{self.mid}"
        return self._msg(chat_id, text=caption, markup=markup, kind=kind, photo=[{"file_id": fid}] if kind == "photo" else None, video={"file_id": fid} if kind == "video" else None)
    def edit_markup(self, chat_id, message_id, markup=None): self._rec("editMarkup", chat_id=chat_id, message_id=message_id, markup=markup); return True
    def edit_text(self, chat_id, message_id, text, markup=None, parse_mode="HTML"): self._rec("editText", chat_id=chat_id, message_id=message_id, text=text); return {"message_id": message_id}
    def edit_caption(self, chat_id, message_id, caption, markup=None, parse_mode="HTML"): self._rec("editCaption", chat_id=chat_id, message_id=message_id, caption=caption); return {"message_id": message_id}
    def answer(self, cb_id, text="", alert=False): self._rec("answer", text=text); return True
    def create_invite(self, chat_id, name="", expire=None):
        self._rec("createInvite", chat_id=chat_id)
        return {"invite_link": f"https://t.me/+fake{chat_id}x{self.mid}"}
    def approve_join(self, chat_id, user_id): self._rec("approveJoin", chat_id=chat_id, user_id=user_id); return True
    def decline_join(self, chat_id, user_id): self._rec("declineJoin", chat_id=chat_id, user_id=user_id); return True
    def kick(self, chat_id, user_id): self._rec("kick", chat_id=chat_id, user_id=user_id); self.members[(chat_id, user_id)] = "left"
    def get_member(self, chat_id, user_id):
        self._rec("getMember", chat_id=chat_id, user_id=user_id)
        if user_id == self.me["id"]:
            return dict(self.chat_rights)
        return {"status": self.members.get((chat_id, user_id), "member")}
    def get_chat(self, chat_id): self._rec("getChat", chat_id=chat_id); return {"id": chat_id, "title": f"Guruh {chat_id}", "bio": "Fake bio"}
    def user_photos(self, user_id): return {"total_count": 1, "photos": [[{"file_id": "avatar1"}]]}
    def set_name(self, name): self._rec("setName", name=name); return True
    def set_description(self, text): self._rec("setDescription", text=text); return True
    def set_about(self, text): self._rec("setAbout", text=text); return True
    def set_commands(self, cmds, scope=None): self._rec("setCommands", commands=cmds, scope=scope); return True
    def set_menu_button(self): self._rec("setMenu"); return True
    def set_photo(self, path): self._rec("setPhoto", path=path); return True

    def file_bytes(self, file_id):
        import base64
        return base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

    def names(self): return [c[0] for c in self.calls]


_FAKES: dict[int, FakeBotAPI] = {}


def get_api(project) -> BotAPI | FakeBotAPI | None:
    if settings.USE_FAKES:
        return _FAKES.setdefault(project.pk, FakeBotAPI())
    t = project.token()
    return BotAPI(t) if t else None
