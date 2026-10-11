"""Instagram rasmlari/zaxira video uchun vaqtinchalik OCHIQ havola. Bepul: Cloudflare Worker + KV (TTL bilan
o'zi o'chadi). Zaxira: Cloudflare R2 (9 GB chegara bilan). Tizim tashqaridan ochiq emas, shuning uchun kerak."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta

import requests
from django.db.models import Sum
from django.utils import timezone

from apps.connections.base import PlatformError, TransientError
from apps.core.notify import notify
from apps.core.settings_store import get_secret, get_setting

from .models import TempObject

KV_MAX = 24 * 1024 * 1024  # KV qiymat chegarasi 25 MB


class WaitingForSpace(Exception):
    pass


class WorkerKVHost:
    """Cloudflare Worker (admin token bilan) orqali KV'ga yuklaydi; TTL tugagach o'zi o'chadi. Bepul."""
    name = "worker_kv"

    def available(self, size: int) -> bool:
        return bool(get_secret("worker.admin_token") and get_setting("worker.cloudflare_url")) and size <= KV_MAX

    def _base(self):
        return get_setting("worker.cloudflare_url").rstrip("/")

    def _h(self):
        return {"Authorization": f"Bearer {get_secret('worker.admin_token')}"}

    def upload(self, path: str, key: str, ttl_sec: int) -> str:
        with open(path, "rb") as f:
            try:
                r = requests.put(f"{self._base()}/admin/tmp/{key}", params={"ttl": max(ttl_sec, 60)}, headers=self._h(), data=f, timeout=120)
            except requests.RequestException as e:
                raise TransientError(f"Worker'ga yuklab bo'lmadi: {e}") from e
        if r.status_code >= 400:
            raise TransientError(f"Worker yuklash xatosi {r.status_code}: {r.text[:200]}")
        return f"{self._base()}/tmp/{key}"

    def delete(self, key: str) -> None:
        try:
            requests.delete(f"{self._base()}/admin/tmp/{key}", headers=self._h(), timeout=30)
        except requests.RequestException:
            pass


class R2Host:
    name = "r2"

    def available(self, size: int) -> bool:
        return all([get_setting("r2.account_id"), get_secret("r2.access_key_id"), get_secret("r2.secret_access_key"), get_setting("r2.bucket")])

    def _client(self):
        import boto3
        return boto3.client("s3", endpoint_url=f"https://{get_setting('r2.account_id')}.r2.cloudflarestorage.com",
                            aws_access_key_id=get_secret("r2.access_key_id"), aws_secret_access_key=get_secret("r2.secret_access_key"),
                            region_name="auto")

    def upload(self, path: str, key: str, ttl_sec: int) -> str:
        c = self._client()
        c.upload_file(path, get_setting("r2.bucket"), key)
        return self.url_for(key, ttl_sec)

    def url_for(self, key: str, ttl_sec: int = 6 * 3600) -> str:
        """Imzolangan vaqtinchalik havola (R2 uchun eng ko'pi 7 kun)."""
        return self._client().generate_presigned_url("get_object", Params={"Bucket": get_setting("r2.bucket"), "Key": key},
                                                     ExpiresIn=min(max(ttl_sec, 3600), 7 * 24 * 3600))

    def test(self) -> str:
        """Ulanishni tekshiradi; xato bo'lsa matn qaytaradi, yaxshi bo'lsa ''."""
        try:
            self._client().head_bucket(Bucket=get_setting("r2.bucket"))
            return ""
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            for secret in (get_secret("r2.secret_access_key"), get_secret("r2.access_key_id")):
                if secret:
                    msg = msg.replace(secret, "***")
            return msg[:250]

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=get_setting("r2.bucket"), Key=key)

    def list_keys(self) -> list[str]:
        c = self._client()
        out, token = [], None
        while True:
            kw = {"Bucket": get_setting("r2.bucket"), **({"ContinuationToken": token} if token else {})}
            r = c.list_objects_v2(**kw)
            out += [o["Key"] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return out
            token = r["NextContinuationToken"]


class FakeHost:
    name = "fake"
    store: dict[str, int] = {}

    def available(self, size): return True
    def upload(self, path, key, ttl_sec):
        FakeHost.store[key] = os.path.getsize(path)
        return f"https://tmp.example/{key}"
    def delete(self, key): FakeHost.store.pop(key, None)
    def list_keys(self): return list(FakeHost.store)


def hosts(fake: bool):
    if fake:
        return [FakeHost()]
    mode = get_setting("publish.use_r2", "auto")
    if mode == "always":
        return [R2Host()]
    return [WorkerKVHost(), R2Host()]


def r2_used_bytes() -> int:
    return TempObject.objects.filter(backend="r2", status="uploaded").aggregate(s=Sum("size"))["s"] or 0


def r2_limit_bytes() -> int:
    return int(float(get_setting("publish.r2.max_gb", 9)) * 1024 ** 3)


def retention_manual() -> bool:
    return get_setting("cloud.retention", "manual") == "manual"


def configured(fake: bool = False) -> bool:
    return fake or R2Host().available(0) or bool(get_secret("worker.admin_token") and get_setting("worker.cloudflare_url"))


def _pick_host(size: int, fake: bool):
    cap = int(float(get_setting("publish.r2.max_gb", 9)) * 1024 ** 3)
    last: Exception | None = None
    for h in hosts(fake):
        if not h.available(size):
            continue
        if h.name == "r2" and r2_used_bytes() + size > cap:
            notify("r2.full", "R2 to'lgan", f"Hajm chegarasi {cap / 1024 ** 3:.0f} GB; ortiqcha fayllarni Cloudflare menyusidan o'chiring.", severity="warn", dedupe_key="r2full")
            last = WaitingForSpace("R2 joyi yetmaydi")
            continue
        return h, None
    return None, last


def _life(host_name: str, ttl_hours):
    """(ttl soniya, delete_after) — qo'lda o'chirish rejimida R2 faylga muddat qo'yilmaydi."""
    if ttl_hours is None:
        if retention_manual() and host_name != "worker_kv":
            return 7 * 24 * 3600, None
        hours = 24 * 30 if host_name == "worker_kv" else 3
    else:
        hours = ttl_hours
    return hours * 3600, timezone.now() + timedelta(hours=hours)


def host_file(path: str, item=None, *, fake: bool = False, ttl_hours: int | None = None, asset=None, business=None, obj: TempObject | None = None) -> TempObject:
    """Faylni Cloudflare'ga yuklaydi. obj berilsa (kutayotgan yozuv) — o'sha yangilanadi."""
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    key = obj.key if obj else f"{uuid.uuid4().hex}{ext}"
    h, last = _pick_host(size, fake)
    if h is not None:
        ttl, after = _life(h.name, ttl_hours)
        try:
            url = h.upload(path, key, ttl)
        except PlatformError as e:
            last = e
        else:
            fields = dict(backend=h.name, size=size, public_url=url, status="uploaded", error="", delete_after=after)
            if obj:
                for k, v in fields.items():
                    setattr(obj, k, v)
                obj.save()
                return obj
            return TempObject.objects.create(key=key, item=item, asset=asset, business=business or (item.business if item else None),
                                             filename=os.path.basename(path)[:200], **fields)
    if isinstance(last, WaitingForSpace):
        raise last
    raise TransientError("Vaqtinchalik hosting sozlanmagan (Worker KV yoki R2).",
                         user_message_uz="Fayl uchun Cloudflare xizmati sozlanmagan: Sozlamalarda Cloudflare R2 (yoki Worker KV) ni kiriting.") from last


def register_pending(asset, *, fake: bool = False) -> TempObject | None:
    """Saqlangan media uchun «yuklanmoqda» yozuvi (Cloudflare menyusida ko'rinadi). Cloud sozlanmagan bo'lsa None."""
    if not get_setting("cloud.auto_upload", True) or not configured(fake):
        return None
    if asset.cloud_id or TempObject.objects.filter(asset=asset).exclude(status="deleted").exists():
        return None
    ext = os.path.splitext(asset.file.name)[1].lower()
    return TempObject.objects.create(key=f"{uuid.uuid4().hex}{ext}", status="pending", item=asset.item, asset=asset, business=asset.item.business,
                                     size=asset.size or 0, filename=(asset.original_name or os.path.basename(asset.file.name))[:200])


def upload_pending(obj: TempObject, *, fake: bool = False) -> TempObject:
    path = obj.asset.file.path if obj.asset_id and obj.asset.file else (obj.local_path or None)
    if not path or not os.path.exists(path):
        obj.status, obj.error = "failed", "Asl fayl topilmadi"
        obj.save(update_fields=["status", "error"])
        return obj
    try:
        res = host_file(path, obj.item, fake=fake, asset=obj.asset, obj=obj)
        if obj.local_path and not obj.asset_id:   # qo'lda yuklangan: mahalliy nusxa kerak emas
            try:
                os.remove(obj.local_path)
            except OSError:
                pass
            obj.local_path = ""
            obj.save(update_fields=["local_path"])
        return res
    except WaitingForSpace:
        obj.status, obj.error = "failed", "Cloudflare joyi to'lgan — keraksiz fayllarni o'chiring"
    except PlatformError as e:
        obj.status, obj.error = "failed", (getattr(e, "user_message_uz", "") or str(e))[:300]
    obj.save(update_fields=["status", "error"])
    return obj


def view_url(obj: TempObject) -> str:
    """Menyuda ko'rsatish uchun (bazaga yozmaydi)."""
    if obj.status == "uploaded" and obj.backend == "r2":
        try:
            return R2Host().url_for(obj.key, 3600)
        except Exception:  # noqa: BLE001
            return ""
    return obj.public_url if obj.status == "uploaded" else ""


def fresh_url(obj: TempObject, ttl_sec: int = 6 * 3600) -> str:
    """Faylga hozir ishlaydigan havola (R2 uchun yangidan imzolanadi) va uni saqlaydi."""
    if obj.status != "uploaded":
        return obj.public_url
    if obj.backend == "r2":
        obj.public_url = R2Host().url_for(obj.key, ttl_sec)
        obj.save(update_fields=["public_url"])
    return obj.public_url


def delete_object(obj: TempObject, *, fake: bool = False) -> None:
    for h in (hosts(fake) + [WorkerKVHost(), R2Host()]) if obj.backend else []:
        if h.name == obj.backend:
            try:
                h.delete(obj.key)
            except Exception:  # noqa: BLE001
                pass
            break
    obj.status = "deleted"
    obj.save(update_fields=["status"])


def worker_status() -> dict:
    """Cloudflare Worker'ning holatini tekshiradi (sozlamalardagi «Tekshirish» tugmasi uchun)."""
    from django.conf import settings
    if settings.USE_FAKES:
        return {"ok": True, "version": "fake"}
    base, token = get_setting("worker.cloudflare_url", "").rstrip("/"), get_secret("worker.admin_token")
    if not base or not token:
        raise PlatformError("Worker sozlanmagan", user_message_uz="Cloudflare Worker manzili va admin tokeni Sozlamalarda kiritilmagan.")
    try:
        r = requests.get(base + "/admin/status", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except requests.RequestException as e:
        raise TransientError(str(e)) from e
    if r.status_code >= 400:
        raise PlatformError(f"Worker {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}
