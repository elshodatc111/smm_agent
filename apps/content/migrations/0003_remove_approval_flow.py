from django.db import migrations


def forwards(apps, schema_editor):
    Item = apps.get_model("content", "ContentItem")
    Item.objects.filter(status="pending_approval").update(status="draft")
    Item.objects.filter(status="approved", scheduled_at__isnull=False).update(status="scheduled")
    Item.objects.filter(status="approved", scheduled_at__isnull=True).update(status="draft")


class Migration(migrations.Migration):
    dependencies = [("content", "0002_initial")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
