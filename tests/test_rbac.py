import pytest

from apps.accounts.models import Role, User, UserBusinessAccess, UserPermissionOverride
from apps.accounts.services import guard_admin_change, delete_role, perms, set_role_permissions
from apps.businesses.scoping import scoped


def test_admin_sees_all(admin, biz, biz2):
    assert perms.can(admin, "settings.configure")
    assert set(perms.businesses_for(admin)) == {biz, biz2}


def test_user_only_assigned_business(user_smm, biz, biz2):
    assert perms.can(user_smm, "calendar.create", biz)
    assert not perms.can(user_smm, "calendar.create", biz2)
    assert list(perms.businesses_for(user_smm)) == [biz]


def test_role_per_business_differs(user_smm, biz, biz2):
    UserBusinessAccess.objects.create(user=user_smm, business=biz2, role=Role.objects.get(name="Analitik"))
    assert perms.can(user_smm, "calendar.create", biz)
    assert not perms.can(user_smm, "calendar.create", biz2)
    assert perms.can(user_smm, "reports.export", biz2)


def test_all_businesses_flag(db, biz, biz2):
    u = User.objects.create_user("a", password="x12345678")
    UserBusinessAccess.objects.create(user=u, business=None, all_flag=True, role=Role.objects.get(name="Analitik"))
    assert perms.can(u, "analytics.view", biz) and perms.can(u, "analytics.view", biz2)


def test_override_and_instant_effect(user_smm, biz):
    assert not perms.can(user_smm, "competitors.delete", biz)
    UserPermissionOverride.objects.create(user=user_smm, code="competitors.delete", allow=True)
    assert perms.can(user_smm, "competitors.delete", biz)
    UserPermissionOverride.objects.create(user=user_smm, code="calendar.create", allow=False)
    assert not perms.can(user_smm, "calendar.create", biz)


def test_role_change_takes_effect_immediately(user_smm, biz):
    role = Role.objects.get(name="SMM mutaxassis")
    assert perms.can(user_smm, "calendar.create", biz)
    set_role_permissions(role, {"dashboard.view"})
    assert not perms.can(user_smm, "calendar.create", biz)


def test_unknown_code_rejected(admin):
    with pytest.raises(ValueError):
        perms.can(admin, "nope.view")


def test_last_admin_protected(admin):
    with pytest.raises(PermissionError):
        guard_admin_change(admin, deactivating=True)


def test_role_with_users_cannot_be_deleted(user_smm):
    with pytest.raises(PermissionError):
        delete_role(Role.objects.get(name="SMM mutaxassis"))


def test_scoped_queryset_isolation(user_smm, biz, biz2):
    from apps.connections.models import SocialAccount
    SocialAccount.objects.create(business=biz, platform="telegram", name="A")
    SocialAccount.objects.create(business=biz2, platform="telegram", name="B")
    assert [a.name for a in scoped(SocialAccount, user_smm)] == ["A"]
    assert not scoped(SocialAccount, user_smm, biz2).exists()
