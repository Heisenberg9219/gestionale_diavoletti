from decimal import Decimal

from django.db import migrations


def seed_initial_data(apps, schema_editor):
    ShopSettings = apps.get_model("core", "ShopSettings")
    Location = apps.get_model("core", "Location")
    TaxRate = apps.get_model("core", "TaxRate")

    ShopSettings.objects.get_or_create(
        singleton_key=True,
        defaults={
            "shop_name": "I Diavoletti",
            "timezone": "Europe/Rome",
            "currency_code": "EUR",
            "default_markup": Decimal("2.500"),
            "return_credit_months": 6,
            "price_rounding_strategy": "NEAREST_90",
        },
    )

    Location.objects.get_or_create(
        code="SALES_FLOOR",
        defaults={
            "name": "Area vendita",
            "type": "SALES_FLOOR",
            "is_active": True,
        },
    )

    Location.objects.get_or_create(
        code="STOCKROOM",
        defaults={
            "name": "Magazzino interno",
            "type": "STOCKROOM",
            "is_active": True,
        },
    )

    TaxRate.objects.get_or_create(
        code="VAT22",
        defaults={
            "name": "IVA ordinaria",
            "percentage": Decimal("22.00"),
            "is_default": True,
            "is_active": True,
        },
    )


def remove_initial_data(apps, schema_editor):
    ShopSettings = apps.get_model("core", "ShopSettings")
    Location = apps.get_model("core", "Location")
    TaxRate = apps.get_model("core", "TaxRate")

    TaxRate.objects.filter(code="VAT22").delete()
    Location.objects.filter(
        code__in=["SALES_FLOOR", "STOCKROOM"]
    ).delete()
    ShopSettings.objects.filter(singleton_key=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_initial_data,
            remove_initial_data,
        ),
    ]