from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]
    operations = [migrations.AddField(model_name="expense", name="notifications_enabled", field=models.BooleanField(default=False))]
