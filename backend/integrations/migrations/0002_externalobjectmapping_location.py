from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="externalobjectmapping",
            name="object_type",
            field=models.CharField(
                choices=[
                    ("PRODUCT", "Prodotto"),
                    ("VARIANT", "Variante"),
                    ("LOCATION", "Sede"),
                    ("CUSTOMER", "Cliente"),
                    ("ORDER", "Ordine"),
                ],
                max_length=24,
            ),
        ),
    ]
