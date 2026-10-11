from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("links", "0002_remove_shortlink_campaign"),
    ]

    operations = [
        migrations.DeleteModel(name="LinkClick"),
        migrations.DeleteModel(name="ShortLink"),
        migrations.DeleteModel(name="WorkerStatus"),
    ]
