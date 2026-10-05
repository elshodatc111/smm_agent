from django.db import migrations


def add_section(apps, schema_editor):
    U = apps.get_model("tgbot", "ClientBotUser")
    for u in U.objects.all():
        changed = False
        for k, v in list((u.sections or {}).items()):
            if isinstance(v, list) and "publish_notice" not in v:
                v.append("publish_notice")
                changed = True
        if changed:
            u.save(update_fields=["sections"])


class Migration(migrations.Migration):
    dependencies = [("tgbot", "0002_clientnotice")]
    operations = [migrations.RunPython(add_section, migrations.RunPython.noop)]
