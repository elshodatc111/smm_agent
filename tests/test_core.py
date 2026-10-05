import pytest

from apps.core import crypto
from apps.core.logging_utils import scrub
from apps.core.models import AuditLog
from apps.core.audit import audit
from apps.core.settings_store import get_setting, set_setting, masked


def test_crypto_roundtrip_and_mask():
    t = crypto.encrypt("sekret-qiymat-1234")
    assert "sekret" not in t
    assert crypto.decrypt(t) == "sekret-qiymat-1234"
    assert crypto.mask("abcdefgh1234") == "••••1234"


def test_secret_setting_encrypted_in_db(admin):
    from apps.core.models import SystemSetting
    set_setting("scrapecreators.api_key", "KEY-123456", user=admin)
    row = SystemSetting.objects.get(key="scrapecreators.api_key")
    assert row.is_secret and row.value is None and "KEY-123456" not in row.value_enc
    assert get_setting("scrapecreators.api_key") == "KEY-123456"
    assert masked("scrapecreators.api_key") == "••••3456"


def test_defaults_and_override(admin):
    assert get_setting("publish.r2.max_gb") == 9
    set_setting("publish.r2.max_gb", 5, user=admin)
    assert get_setting("publish.r2.max_gb") == 5


def test_audit_append_only(admin):
    audit("x", user=admin)
    a = AuditLog.objects.first()
    with pytest.raises(PermissionError):
        a.delete()
    a.action = "y"
    with pytest.raises(PermissionError):
        a.save()


@pytest.mark.parametrize("raw", [
    "url https://api.telegram.org/bot123456789:AAEhBP0av28dTuw8vDwZTVkFp7xaIFOQVjk/getMe",
    'headers {"authorization": "Bearer abcdefghij1234567890"}',
    "key=AIzaSyA1234567890abcdefghijklmnopqrstu",
    "token gsk_abcdefghijklmnopqrstuvwxyz",
])
def test_log_scrubber(raw):
    out = scrub(raw)
    assert "AAEhBP0av28" not in out and "abcdefghij1234567890" not in out
    assert "AIzaSyA1234567890" not in out and "gsk_abcdefghijkl" not in out
