from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0003_lead_dailystat"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dailystat",
            name="leads",
        ),
        migrations.DeleteModel(
            name="Lead",
        ),
    ]
