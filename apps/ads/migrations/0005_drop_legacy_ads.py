from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ads", "0004_adproposal"),
        ("links", "0002_remove_shortlink_campaign"),
    ]

    operations = [
        migrations.DeleteModel(name="AdResult"),
        migrations.DeleteModel(name="AdRecommendation"),
        migrations.DeleteModel(name="AdCampaign"),
    ]
