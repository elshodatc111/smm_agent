"""Olib tashlangan «Onlayn kanal» moduli qoldiqlari bootstrap orqali tozalanadi."""
import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

pytestmark = pytest.mark.django_db(transaction=True)


def test_bootstrap_drops_online_leftovers():
    with connection.cursor() as c:
        c.execute("CREATE TABLE online_onlineproject (id integer primary key, name varchar(10))")
        c.execute("CREATE TABLE online_lead (id integer primary key, p integer)")
    MigrationRecorder(connection).ensure_schema()
    MigrationRecorder.Migration.objects.create(app="online", name="0001_initial")
    call_command("bootstrap")
    assert not [t for t in connection.introspection.table_names() if t.startswith("online_")]
    assert not MigrationRecorder.Migration.objects.filter(app="online").exists()
    call_command("bootstrap")      # qayta ishga tushirsa xavfsiz
