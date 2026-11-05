from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_classifier")]

    operations = [
        migrations.AddField(
            model_name="botdialog",
            name="screen_message_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
