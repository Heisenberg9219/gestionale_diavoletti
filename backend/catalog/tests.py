from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import TaxRate

from .models import (
    Category,
    Color,
    Product,
    ProductBarcode,
    ProductVariant,
    Size,
    SizeScale,
)


class ProductCatalogModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tax_rate = TaxRate.objects.create(
            code="TEST_VAT22",
            name="IVA test 22%",
            percentage="22.00",
        )
        cls.category = Category.objects.create(
            code="TEST_CATEGORY",
            name="Categoria test",
        )
        cls.color = Color.objects.create(
            code="TEST_RED",
            name="Rosso test",
        )
        cls.size_scale = SizeScale.objects.create(
            code="TEST_AGE",
            name="Età test",
            scale_type=SizeScale.Type.AGE,
        )
        cls.size = Size.objects.create(
            size_scale=cls.size_scale,
            code="TEST_6A",
            label="6 anni",
            display_order=1,
        )
        cls.other_size = Size.objects.create(
            size_scale=cls.size_scale,
            code="TEST_8A",
            label="8 anni",
            display_order=2,
        )
        cls.product = Product.objects.create(
            code="TEST_PRODUCT",
            name="Prodotto test",
            category=cls.category,
            tax_rate=cls.tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product,
            sku="TEST_SKU_6_RED",
            color=cls.color,
            size=cls.size,
        )
        cls.other_variant = ProductVariant.objects.create(
            product=cls.product,
            sku="TEST_SKU_8_RED",
            color=cls.color,
            size=cls.other_size,
        )

    def test_product_variant_relationship(self):
        self.assertEqual(self.variant.product, self.product)
        self.assertIn(self.variant, self.product.variants.all())

    def test_duplicate_product_color_size_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductVariant.objects.create(
                    product=self.product,
                    sku="TEST_DUPLICATE_SKU",
                    color=self.color,
                    size=self.size,
                )

    def test_only_one_primary_barcode_per_variant(self):
        ProductBarcode.objects.create(
            variant=self.variant,
            code="TEST_PRIMARY_001",
            barcode_type=ProductBarcode.Type.CODE128,
            source=ProductBarcode.Source.INTERNAL,
            is_primary=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductBarcode.objects.create(
                    variant=self.variant,
                    code="TEST_PRIMARY_002",
                    barcode_type=ProductBarcode.Type.EAN13,
                    source=ProductBarcode.Source.MANUFACTURER,
                    is_primary=True,
                )

    def test_barcode_code_is_globally_unique(self):
        ProductBarcode.objects.create(
            variant=self.variant,
            code="TEST_SHARED_BARCODE",
            barcode_type=ProductBarcode.Type.EAN13,
            source=ProductBarcode.Source.MANUFACTURER,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductBarcode.objects.create(
                    variant=self.other_variant,
                    code="TEST_SHARED_BARCODE",
                    barcode_type=ProductBarcode.Type.EAN13,
                    source=ProductBarcode.Source.MANUFACTURER,
                )