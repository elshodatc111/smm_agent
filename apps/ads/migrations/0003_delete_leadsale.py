from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0002_initial"),
    ]

    operations = [
        migrations.DeleteModel(
            name="LeadSale",
        ),
    ]
