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

    def upload(self, path: str, key: str, ttl_sec: int, progress=None) -> str:
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


_BUCKET_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9.\-_]{1,62}$")


def r2_bucket() -> str:
    """Bucket nomi. Foydalanuvchi URL kiritib qo'ygan bo'lsa (https://<id>.r2.cloudflarestorage.com/<bucket>) nomini ajratib oladi;
    nom topilmasa PlatformError (tushunarli matn bilan) ko'taradi."""
    raw = (get_setting("r2.bucket") or "").strip()
    if raw.lower().startswith(("http://", "https://")) or "cloudflarestorage.com" in raw.lower():
        from urllib.parse import urlparse
        path = urlparse(raw if "://" in raw else "https://" + raw).path.strip("/")
        raw = path.split("/")[0] if path else ""
    if not _BUCKET_RE.match(raw.lower()):
        raise PlatformError("R2 bucket nomi noto'g'ri", user_message_uz=(
            "«R2 Bucket» maydoniga URL emas, faqat bucket NOMI yozilishi kerak (masalan: smm-media). "
            "Nomni Cloudflare → R2 → Buckets ro'yxatidan ko'ring va Sozlamalar → Kalitlar'da to'g'rilang."))
    return raw


class R2Host:
    name = "r2"

    def available(self, size: int) -> bool:
        return all([get_setting("r2.account_id"), get_secret("r2.access_key_id"), get_secret("r2.secret_access_key"), get_setting("r2.bucket")])

    def _client(self):
        import boto3
        from botocore.config import Config
        return boto3.client("s3", config=Config(connect_timeout=15, read_timeout=120, retries={"max_attempts": 4, "mode": "standard"}), endpoint_url=f"https://{get_setting('r2.account_id')}.r2.cloudflarestorage.com",
                            aws_access_key_id=get_secret("r2.access_key_id"), aws_secret_access_key=get_secret("r2.secret_access_key"),
                            region_name="auto")

    def upload(self, path: str, key: str, ttl_sec: int, progress=None) -> str:
        """8 MB li bo'laklar bilan parallel (multipart) yuklaydi; progress(foiz) chaqiriladi."""
        from boto3.s3.transfer import TransferConfig
        c = self._client()
        total = max(os.path.getsize(path), 1)
        done = [0]

        def cb(n):
            done[0] += n
            if progress:
                progress(min(99, int(done[0] * 100 / total)))
        mb = 1024 * 1024
        c.upload_file(path, r2_bucket(), key, Callback=cb, Config=TransferConfig(multipart_threshold=8 * mb, multipart_chunksize=8 * mb, max_concurrency=4))
        return self.url_for(key, ttl_sec)

    def url_for(self, key: str, ttl_sec: int = 6 * 3600) -> str:
        """Imzolangan vaqtinchalik havola (R2 uchun eng ko'pi 7 kun)."""
        return self._client().generate_presigned_url("get_object", Params={"Bucket": r2_bucket(), "Key": key},
                                                     ExpiresIn=min(max(ttl_sec, 3600), 7 * 24 * 3600))

    def test(self) -> str:
        """Ulanishni tekshiradi; xato bo'lsa matn qaytaradi, yaxshi bo'lsa ''."""
        try:
            c = self._client()
            key = f"_test/{uuid.uuid4().hex}.txt"
            # HeadBucket ba'zi bucket-cheklangan kalitlarda 403 beradi, shuning uchun haqiqiy amal (yozish/o'qish/o'chirish) bilan tekshiramiz
            c.put_object(Bucket=r2_bucket(), Key=key, Body=b"ok")
            c.get_object(Bucket=r2_bucket(), Key=key)["Body"].read()
            c.delete_object(Bucket=r2_bucket(), Key=key)
            return ""
        except PlatformError as e:
            return e.user_message_uz
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "403" in msg or "AccessDenied" in msg or "Forbidden" in msg:
                return ("Kalitga bu bucket («%s») uchun yozish ruxsati berilmagan (403). Cloudflare → R2 → Manage API Tokens'da kalitni "
                        "«Object Read & Write» ruxsati va aynan shu bucket (yoki barcha bucketlar) uchun yarating va yangi Access Key/Secret ni kiriting." % get_setting("r2.bucket"))
            for secret in (get_secret("r2.secret_access_key"), get_secret("r2.access_key_id")):
                if secret:
                    msg = msg.replace(secret, "***")
            return msg[:250]

    def delete(self, key: str) -> None:
        self._client().delete_object(Bucket=r2_bucket(), Key=key)

    def list_keys(self) -> list[str]:
        c = self._client()
        out, token = [], None
        while True:
            kw = {"Bucket": r2_bucket(), **({"ContinuationToken": token} if token else {})}
            r = c.list_objects_v2(**kw)
            out += [o["Key"] for o in r.get("Contents", [])]
            if not r.get("IsTruncated"):
                return out
            token = r["NextContinuationToken"]


class FakeHost:
    name = "fake"
    store: dict[str, int] = {}

    def available(self, size): return True
    def upload(self, path, key, ttl_sec, progress=None):
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


def host_file(path: str, item=None, *, fake: bool = False, ttl_hours: int | None = None, asset=None, business=None, obj: TempObject | None = None, progress=None) -> TempObject:
    """Faylni Cloudflare'ga yuklaydi. obj berilsa (kutayotgan yozuv) — o'sha yangilanadi."""
    size = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()
    key = obj.key if obj else f"{uuid.uuid4().hex}{ext}"
    h, last = _pick_host(size, fake)
    if h is not None:
        ttl, after = _life(h.name, ttl_hours)
        try:
            url = h.upload(path, key, ttl, progress=progress)
        except PlatformError as e:
            last = e
        else:
            fields = dict(backend=h.name, size=size, public_url=url, status="uploaded", error="", delete_after=after, progress=100)
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
    last = [-1]

    def progress(pct: int) -> None:
        if pct != last[0]:
            last[0] = pct
            TempObject.objects.filter(pk=obj.pk).update(progress=pct)
    obj.progress, obj.error = 0, ""
    obj.save(update_fields=["progress", "error"])
    try:
        res = host_file(path, obj.item, fake=fake, asset=obj.asset, obj=obj, progress=progress)
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
    except Exception as e:  # noqa: BLE001 — qotib qolmasin: har qanday xato "Xato" holati va tushunarli matn bilan ko'rinadi
        obj.status, obj.error = "failed", _friendly(e)
    obj.save(update_fields=["status", "error"])
    return obj


def _friendly(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "bucket" in low and ("invalid" in low or "nosuchbucket" in low or "does not exist" in low):
        return "R2 bucket topilmadi yoki nomi noto'g'ri. Sozlamalar → Kalitlar'da «R2 Bucket» maydoniga faqat nom yozing."
    if "accessdenied" in low or "invalidaccesskey" in low or "signature" in low or "403" in low:
        return "R2 kaliti noto'g'ri yoki ruxsat yo'q (Access Key / Secret / Account ID ni tekshiring)."
    if "timed out" in low or "timeout" in low or "connection" in low:
        return "Cloudflare'ga ulanishda tarmoq xatosi. Qayta urinib ko'ring."
    for sec in (get_secret("r2.secret_access_key"), get_secret("r2.access_key_id")):
        if sec:
            msg = msg.replace(sec, "***")
    return ("Yuklash xatosi: " + msg)[:300]


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
