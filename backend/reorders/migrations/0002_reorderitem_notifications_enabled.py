from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reorders", "0001_initial")]
    operations = [migrations.AddField(model_name="reorderitem", name="notifications_enabled", field=models.BooleanField(default=False))]
