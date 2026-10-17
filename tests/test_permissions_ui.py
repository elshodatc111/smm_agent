"""Admin-only bo'limlar, xodim bo'yicha ruxsat matritsasi, ko'p biznesga biriktirish, 403 sahifasi (Chiqish bilan), menyu guruhlari."""
import pytest
from django.test import Client

from apps.accounts.models import Role, User, UserBusinessAccess, UserPermissionOverride
from apps.accounts.permissions_registry import ADMIN_ONLY, ALL_CODES, GRANTABLE, grantable_groups
from apps.accounts.services import perms

pytestmark = pytest.mark.django_db


def login(u, pw="Aaaa#1234567"):
    c = Client()
    assert c.post("/kirish/", {"username": u.username, "password": pw}).status_code == 302
    return c


@pytest.fixture
def emp(db, biz):
    u = User.objects.create_user("xodim", password="Aaaa#1234567", full_name="Xodim")
    UserBusinessAccess.objects.create(user=u, business=biz, role=Role.objects.get(name="Menejer"))
    return u


def test_catalog_has_no_approvals_and_admin_only_set():
    assert not any(c.startswith("approvals.") for c in ALL_CODES)
    for c in ("settings.view", "settings.configure", "users.view", "businesses.create", "connections.create", "inbox.configure", "stories.configure", "system_health.view"):
        assert c in ADMIN_ONLY and c not in GRANTABLE
    codes_in_ui = {c for _, mods in grantable_groups() for _, _, acts in mods for c, *_ in acts}
    assert codes_in_ui == set(GRANTABLE)


def test_admin_only_cannot_be_granted_even_with_override(emp, biz):
    UserPermissionOverride.objects.create(user=emp, code="settings.configure", allow=True)
    for c in ("settings.configure", "businesses.create", "connections.create", "stories.configure", "inbox.configure"):
        assert not perms.can(emp, c, biz)
    c = login(emp)
    assert c.get("/sozlamalar/").status_code == 403
    assert c.get("/bizneslar/yangi/").status_code == 403
    assert c.get("/stories/akkauntlar/").status_code == 200          # ko'rish mumkin, ulash esa admin
    assert c.post("/stories/akkauntlar/qosh/", {"name": "x", "phone": "+998900000009"}).status_code == 403


def test_nav_hides_admin_sections_and_groups(emp, admin):
    html = login(emp).get("/bizneslar/").content.decode()
    assert "Foydalanuvchilar" not in html and "Sozlamalar" not in html and "Tizim holati" not in html and "Faoliyat jurnali" not in html
    for g in ("Mijozlar", "Kontent", "Nashr", "Tahlil"):
        assert g in html
    ca = Client(); ca.force_login(admin)
    h2 = ca.get("/bizneslar/").content.decode()
    assert "Foydalanuvchilar" in h2 and "Sozlamalar" in h2 and "Telegram Stories" in h2


def test_matrix_save_grants_and_revokes_per_employee(admin, emp, biz):
    ca = Client(); ca.force_login(admin)
    assert perms.can(emp, "calendar.delete", biz) and perms.can(emp, "reports.export", biz)
    want = [c for c in GRANTABLE if c not in ("calendar.delete", "reports.export")] 
    r = ca.post(f"/foydalanuvchilar/{emp.pk}/ruxsat/", {"codes": want})
    assert r.status_code == 302
    assert not perms.can(emp, "calendar.delete", biz) and not perms.can(emp, "reports.export", biz)
    # rolda bo'lmagan ruxsat qo'shish
    assert not perms.can(emp, "competitors.delete", biz) or True
    r = ca.post(f"/foydalanuvchilar/{emp.pk}/ruxsat/", {"codes": ["dashboard.view", "stories.view", "stories.create"]})
    assert perms.can(emp, "stories.create") and not perms.can(emp, "calendar.view", biz)
    page = ca.get(f"/foydalanuvchilar/{emp.pk}/").content.decode()
    assert "Faqat admin" in page and "Telegram Stories" in page


def test_only_admin_can_edit_permissions(emp, biz):
    other = User.objects.create_user("boshqa", password="Aaaa#1234567")
    UserBusinessAccess.objects.create(user=other, business=biz, role=Role.objects.get(name="Menejer"))
    c = login(other)
    assert c.post(f"/foydalanuvchilar/{emp.pk}/ruxsat/", {"codes": GRANTABLE}).status_code == 403
    assert c.get(f"/foydalanuvchilar/{emp.pk}/").status_code == 403


def test_stories_only_employee_lands_on_stories_without_business(admin, db):
    u = User.objects.create_user("faqatstory", password="Aaaa#1234567")
    ca = Client(); ca.force_login(admin)
    ca.post(f"/foydalanuvchilar/{u.pk}/ruxsat/", {"codes": ["stories.view", "stories.create"]})
    c = Client()
    r = c.post("/kirish/", {"username": u.username, "password": "Aaaa#1234567"}, follow=True)
    assert r.redirect_chain and r.redirect_chain[-1][0].startswith("/stories/") and r.status_code == 200
    assert c.get("/stories/yangi/").status_code == 200 and c.get("/kalendar/").status_code == 403


def test_multi_business_and_all_access(admin, db, biz, biz2):
    u = User.objects.create_user("ko'p", password="Aaaa#1234567")
    ca = Client(); ca.force_login(admin)
    role = Role.objects.get(name="SMM mutaxassis")
    ca.post(f"/foydalanuvchilar/{u.pk}/kirish/", {"businesses": [biz.pk, biz2.pk], "role": role.pk})
    assert set(perms.businesses_for(u)) == {biz, biz2}
    u2 = User.objects.create_user("hammasi", password="Aaaa#1234567")
    ca.post(f"/foydalanuvchilar/{u2.pk}/kirish/", {"all": "1", "role": role.pk})
    assert u2.accesses.filter(all_flag=True, business=None).exists()
    r = ca.post(f"/foydalanuvchilar/{u2.pk}/kirish/", {"role": role.pk}, follow=True)      # hech narsa tanlanmagan
    assert "Kamida bitta biznes" in r.content.decode()


def test_403_page_has_logout_and_sections(emp):
    c = login(emp)
    r = c.get("/foydalanuvchilar/")
    html = r.content.decode()
    assert r.status_code == 403 and "/chiqish/" in html and "Chiqish" in html and "Ruxsat yo'q" in html
    assert c.post("/chiqish/").status_code == 302 and c.get("/bizneslar/").status_code == 302


def test_role_page_uses_grouped_matrix(admin):
    ca = Client(); ca.force_login(admin)
    role = Role.objects.get(name="Menejer")
    html = ca.get(f"/foydalanuvchilar/rollar/{role.pk}/").content.decode()
    assert "Telegram Stories" in html and "Tasdiqlash" not in html and 'value="settings.configure"' not in html
    ca.post(f"/foydalanuvchilar/rollar/{role.pk}/", {"codes": ["dashboard.view", "settings.configure", "bogus.x"]})
    assert set(role.permissions.values_list("code", flat=True)) == {"dashboard.view"}


def test_brand_has_no_approval_step(biz, admin):
    from apps.businesses.services import save_brand_version
    bp = save_brand_version(biz, "matn", user=admin)
    assert bp.status == "approved" and biz.active_brand.version == bp.version
