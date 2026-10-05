import pytest
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _setup(db):
    from django.core.cache import cache
    cache.clear()
    from apps.connections import fake
    fake.reset()
    from apps.providers import router
    router.reset_registry()
    call_command("bootstrap")


@pytest.fixture
def admin(db):
    from apps.accounts.models import User
    return User.objects.create_user("admin", password="x12345678", is_admin=True)


@pytest.fixture
def biz(db):
    from apps.businesses.models import Business, BusinessTemplate
    return Business.objects.create(name="Test Markaz", industry="o'quv markaz", template=BusinessTemplate.objects.get(key="oquv_markaz"),
                                   facts={"phones": ["+998901234567"], "prices": ["500000"], "discounts": ["20"]},
                                   contact_info="+998 90 123 45 67", avg_check=500000)


@pytest.fixture
def biz2(db):
    from apps.businesses.models import Business
    return Business.objects.create(name="Boshqa Biznes")


@pytest.fixture
def acc_tg(biz):
    from apps.connections.models import SocialAccount
    return SocialAccount.objects.create(business=biz, platform="telegram", name="Kanal", handle="kanal", external_id="-100123", history_imported=True)


@pytest.fixture
def acc_ig(biz):
    from apps.connections.models import SocialAccount
    return SocialAccount.objects.create(business=biz, platform="instagram", name="IG", handle="ig", external_id="ig1", history_imported=True)


@pytest.fixture
def user_smm(db, biz):
    from apps.accounts.models import Role, User, UserBusinessAccess
    u = User.objects.create_user("smm", password="x12345678")
    UserBusinessAccess.objects.create(user=u, business=biz, role=Role.objects.get(name="SMM mutaxassis"))
    return u


@pytest.fixture
def manager(db, biz):
    from apps.accounts.models import Role, User, UserBusinessAccess
    u = User.objects.create_user("mgr", password="x12345678")
    UserBusinessAccess.objects.create(user=u, business=biz, role=Role.objects.get(name="Menejer"))
    return u
