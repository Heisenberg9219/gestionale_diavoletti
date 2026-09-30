from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        ("vouchers", "0002_voucher_notifications_enabled"),
    ]
    operations = [
        migrations.AddField(
            model_name="voucher",
            name="customer",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="vouchers", to="customers.customer",
            ),
        ),
    ]
