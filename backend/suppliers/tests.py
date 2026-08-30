from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import (
    Category,
    Product,
    ProductVariant,
    Size,
    SizeScale,
)
from core.models import TaxRate

from .models import Supplier, SupplierVariant


class SupplierModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(
            code="SUPPLIER_TEST_VAT",
            name="IVA test fornitori",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="SUPPLIER_TEST_CATEGORY",
            name="Categoria test fornitori",
        )
        size_scale = SizeScale.objects.create(
            code="SUPPLIER_TEST_SCALE",
            name="Scala test fornitori",
            scale_type=SizeScale.Type.AGE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="SUPPLIER_TEST_SIZE",
            label="Taglia test",
        )
        product = Product.objects.create(
            code="SUPPLIER_TEST_PRODUCT",
            name="Prodotto test fornitori",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="SUPPLIER_TEST_SKU",
            size=size,
        )
        cls.supplier = Supplier.objects.create(
            code="SUPPLIER_A",
            business_name="Fornitore A",
            vat_number="IT00000000001",
        )

    def test_duplicate_vat_number_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Supplier.objects.create(
                    code="SUPPLIER_DUPLICATE_VAT",
                    business_name="Fornitore con partita IVA duplicata",
                    vat_number="IT00000000001",
                )

    def test_multiple_suppliers_can_have_blank_vat_number(self):
        Supplier.objects.create(
            code="SUPPLIER_NO_VAT_1",
            business_name="Fornitore senza IVA 1",
        )
        Supplier.objects.create(
            code="SUPPLIER_NO_VAT_2",
            business_name="Fornitore senza IVA 2",
        )

        count = Supplier.objects.filter(vat_number="").count()
        self.assertEqual(count, 2)

    def test_duplicate_supplier_variant_is_rejected(self):
        SupplierVariant.objects.create(
            supplier=self.supplier,
            variant=self.variant,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SupplierVariant.objects.create(
                    supplier=self.supplier,
                    variant=self.variant,
                )

    def test_only_one_preferred_supplier_per_variant(self):
        other_supplier = Supplier.objects.create(
            code="SUPPLIER_B",
            business_name="Fornitore B",
        )
        SupplierVariant.objects.create(
            supplier=self.supplier,
            variant=self.variant,
            is_preferred=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SupplierVariant.objects.create(
                    supplier=other_supplier,
                    variant=self.variant,
                    is_preferred=True,
                )

    def test_minimum_order_quantity_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SupplierVariant.objects.create(
                    supplier=self.supplier,
                    variant=self.variant,
                    minimum_order_quantity=0,
                )