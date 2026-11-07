from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_messenger_platform")]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="max_chat_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
    ]
