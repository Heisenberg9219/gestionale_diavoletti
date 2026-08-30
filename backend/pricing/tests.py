from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from catalog.models import (
    Category,
    Product,
    ProductVariant,
    Size,
    SizeScale,
)
from core.models import TaxRate

from .models import VariantSalePrice


class VariantSalePriceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(
            code="PRICING_TEST_VAT",
            name="IVA test prezzi",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="PRICING_TEST_CATEGORY",
            name="Categoria test prezzi",
        )
        size_scale = SizeScale.objects.create(
            code="PRICING_TEST_SCALE",
            name="Scala test prezzi",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="PRICING_TEST_SIZE",
            label="Taglia unica test",
        )
        product = Product.objects.create(
            code="PRICING_TEST_PRODUCT",
            name="Prodotto test prezzi",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="PRICING_TEST_SKU",
            size=size,
        )

    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VariantSalePrice.objects.create(
                    variant=self.variant,
                    amount="0.00",
                )

    def test_valid_until_must_be_after_valid_from(self):
        valid_from = timezone.now()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VariantSalePrice.objects.create(
                    variant=self.variant,
                    amount="19.90",
                    valid_from=valid_from,
                    valid_until=valid_from,
                )

    def test_only_one_current_price_per_variant(self):
        VariantSalePrice.objects.create(
            variant=self.variant,
            amount="19.90",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VariantSalePrice.objects.create(
                    variant=self.variant,
                    amount="24.90",
                )

    def test_closed_price_and_current_price_can_coexist(self):
        now = timezone.now()

        VariantSalePrice.objects.create(
            variant=self.variant,
            amount="19.90",
            valid_from=now - timedelta(days=30),
            valid_until=now - timedelta(days=1),
        )
        VariantSalePrice.objects.create(
            variant=self.variant,
            amount="24.90",
            valid_from=now,
        )

        self.assertEqual(
            VariantSalePrice.objects.filter(
                variant=self.variant,
            ).count(),
            2,
        )