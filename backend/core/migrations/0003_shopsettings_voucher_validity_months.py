from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_seed_initial_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopsettings",
            name="voucher_validity_months",
            field=models.PositiveSmallIntegerField(
                default=6,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(120),
                ],
            ),
        ),
    ]
