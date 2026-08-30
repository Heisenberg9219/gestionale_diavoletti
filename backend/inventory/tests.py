from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import (
    Category,
    Product,
    ProductVariant,
    Size,
    SizeScale,
)
from core.models import Location, TaxRate

from .models import StockBalance, StockMovement, VariantInventoryCost
from .services import post_stock_movement, transfer_stock


class InventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(
            code="INVENTORY_TEST_VAT",
            name="IVA test inventario",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="INVENTORY_TEST_CATEGORY",
            name="Categoria test inventario",
        )
        size_scale = SizeScale.objects.create(
            code="INVENTORY_TEST_SCALE",
            name="Scala test inventario",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="INVENTORY_TEST_SIZE",
            label="Taglia unica test",
        )
        product = Product.objects.create(
            code="INVENTORY_TEST_PRODUCT",
            name="Prodotto test inventario",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="INVENTORY_TEST_SKU",
            size=size,
        )
        cls.source_location = Location.objects.create(
            code="INVENTORY_TEST_SOURCE",
            name="Ubicazione origine test",
            type=Location.Type.OTHER,
        )
        cls.destination_location = Location.objects.create(
            code="INVENTORY_TEST_DESTINATION",
            name="Ubicazione destinazione test",
            type=Location.Type.OTHER,
        )

    def load_initial_stock(self, quantity, unit_cost):
        return post_stock_movement(
            variant=self.variant,
            location=self.source_location,
            movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=quantity,
            unit_cost=unit_cost,
        )

    def test_initial_stock_updates_balance_and_cost(self):
        self.load_initial_stock(10, "10.00")

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.source_location,
        )
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )

        self.assertEqual(balance.quantity_on_hand, 10)
        self.assertEqual(inventory_cost.total_quantity, 10)
        self.assertEqual(
            inventory_cost.inventory_value,
            Decimal("100.00"),
        )
        self.assertEqual(
            inventory_cost.weighted_average_unit_cost,
            Decimal("10.0000"),
        )

    def test_purchase_receipt_recalculates_weighted_average_cost(self):
        self.load_initial_stock(10, "10.00")

        post_stock_movement(
            variant=self.variant,
            location=self.source_location,
            movement_type=StockMovement.Type.PURCHASE_RECEIPT,
            quantity_delta=10,
            unit_cost="20.00",
        )

        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )

        self.assertEqual(inventory_cost.total_quantity, 20)
        self.assertEqual(
            inventory_cost.inventory_value,
            Decimal("300.00"),
        )
        self.assertEqual(
            inventory_cost.weighted_average_unit_cost,
            Decimal("15.0000"),
        )

    def test_sale_reduces_quantity_at_weighted_average_cost(self):
        self.load_initial_stock(10, "10.00")

        movement = post_stock_movement(
            variant=self.variant,
            location=self.source_location,
            movement_type=StockMovement.Type.SALE,
            quantity_delta=-3,
        )

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.source_location,
        )
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )

        self.assertEqual(balance.quantity_on_hand, 7)
        self.assertEqual(inventory_cost.total_quantity, 7)
        self.assertEqual(
            inventory_cost.inventory_value,
            Decimal("70.00"),
        )
        self.assertEqual(movement.unit_cost, Decimal("10.0000"))

    def test_insufficient_stock_rolls_back_movement(self):
        self.load_initial_stock(2, "10.00")

        with self.assertRaises(ValidationError):
            post_stock_movement(
                variant=self.variant,
                location=self.source_location,
                movement_type=StockMovement.Type.SALE,
                quantity_delta=-3,
            )

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.source_location,
        )
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )

        self.assertEqual(balance.quantity_on_hand, 2)
        self.assertEqual(inventory_cost.total_quantity, 2)
        self.assertEqual(
            StockMovement.objects.filter(
                variant=self.variant,
            ).count(),
            1,
        )

    def test_transfer_moves_stock_without_changing_total_value(self):
        self.load_initial_stock(5, "12.00")

        outgoing, incoming = transfer_stock(
            variant=self.variant,
            source_location=self.source_location,
            destination_location=self.destination_location,
            quantity=2,
        )

        source_balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.source_location,
        )
        destination_balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.destination_location,
        )
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )

        self.assertEqual(source_balance.quantity_on_hand, 3)
        self.assertEqual(destination_balance.quantity_on_hand, 2)
        self.assertEqual(inventory_cost.total_quantity, 5)
        self.assertEqual(
            inventory_cost.inventory_value,
            Decimal("60.00"),
        )
        self.assertEqual(
            outgoing.transfer_group_id,
            incoming.transfer_group_id,
        )

    def test_transfer_requires_different_locations(self):
        self.load_initial_stock(5, "12.00")

        with self.assertRaises(ValidationError):
            transfer_stock(
                variant=self.variant,
                source_location=self.source_location,
                destination_location=self.source_location,
                quantity=1,
            )

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.source_location,
        )
        self.assertEqual(balance.quantity_on_hand, 5)