from decimal import Decimal

from django.contrib.auth import get_user_model
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

from .models import (
    InventoryCountLine,
    InventoryCountSession,
    StockBalance,
    StockMovement,
    VariantInventoryCost,
)
from .services import (
    confirm_inventory_count,
    post_stock_movement,
    record_inventory_count,
    start_inventory_count,
    transfer_stock,
)


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


class PhysicalInventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="inventory-count@example.com",
            password="test-password",
        )
        tax_rate = TaxRate.objects.create(
            code="COUNT_TEST_VAT",
            name="IVA test conteggio",
            percentage="22.00",
        )
        cls.category = Category.objects.create(
            code="COUNT_TEST_CATEGORY",
            name="Categoria test conteggio",
        )
        size_scale = SizeScale.objects.create(
            code="COUNT_TEST_SCALE",
            name="Scala test conteggio",
            scale_type=SizeScale.Type.AGE,
        )
        first_size = Size.objects.create(
            size_scale=size_scale,
            code="COUNT_TEST_SIZE_1",
            label="Taglia test 1",
        )
        second_size = Size.objects.create(
            size_scale=size_scale,
            code="COUNT_TEST_SIZE_2",
            label="Taglia test 2",
        )
        product = Product.objects.create(
            code="COUNT_TEST_PRODUCT",
            name="Prodotto test conteggio",
            category=cls.category,
            tax_rate=tax_rate,
        )
        cls.first_variant = ProductVariant.objects.create(
            product=product,
            sku="COUNT_TEST_SKU_1",
            size=first_size,
        )
        cls.second_variant = ProductVariant.objects.create(
            product=product,
            sku="COUNT_TEST_SKU_2",
            size=second_size,
        )
        cls.location = Location.objects.create(
            code="COUNT_TEST_LOCATION",
            name="Ubicazione test conteggio",
            type=Location.Type.STOCKROOM,
        )

    def setUp(self):
        post_stock_movement(
            variant=self.first_variant,
            location=self.location,
            movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=5,
            unit_cost="10.00",
        )
        post_stock_movement(
            variant=self.second_variant,
            location=self.location,
            movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=2,
            unit_cost="20.00",
        )

    def create_session(self, code="COUNT-2026-001", scope=None):
        return InventoryCountSession.objects.create(
            code=code,
            name="Inventario fisico test",
            location=self.location,
            scope=scope or InventoryCountSession.Scope.FULL,
            created_by=self.user,
        )

    def test_start_creates_historical_snapshot(self):
        session = self.create_session()
        start_inventory_count(session=session)

        session.refresh_from_db()
        first_line = session.lines.get(variant=self.first_variant)
        self.assertEqual(session.status, InventoryCountSession.Status.IN_PROGRESS)
        self.assertEqual(session.lines.count(), 2)
        self.assertEqual(first_line.expected_quantity, 5)
        self.assertEqual(first_line.unit_cost_snapshot, Decimal("10.0000"))
        self.assertEqual(first_line.expected_value, Decimal("50.00"))

    def test_partial_inventory_requires_and_uses_a_scope(self):
        empty_session = self.create_session(
            code="COUNT-2026-EMPTY",
            scope=InventoryCountSession.Scope.PARTIAL,
        )
        with self.assertRaises(ValidationError):
            start_inventory_count(session=empty_session)

        session = self.create_session(
            code="COUNT-2026-PARTIAL",
            scope=InventoryCountSession.Scope.PARTIAL,
        )
        session.variants.add(self.first_variant)
        start_inventory_count(session=session)
        self.assertEqual(session.lines.count(), 1)
        self.assertEqual(session.lines.get().variant, self.first_variant)

    def test_confirmation_creates_gain_and_loss_movements(self):
        session = self.create_session()
        start_inventory_count(session=session)
        record_inventory_count(
            line=session.lines.get(variant=self.first_variant),
            counted_quantity=3,
            counted_by=self.user,
        )
        record_inventory_count(
            line=session.lines.get(variant=self.second_variant),
            counted_quantity=4,
            counted_by=self.user,
        )

        confirm_inventory_count(session=session, confirmed_by=self.user)

        session.refresh_from_db()
        first_balance = StockBalance.objects.get(
            variant=self.first_variant,
            location=self.location,
        )
        second_balance = StockBalance.objects.get(
            variant=self.second_variant,
            location=self.location,
        )
        self.assertEqual(session.status, InventoryCountSession.Status.CONFIRMED)
        self.assertEqual(first_balance.quantity_on_hand, 3)
        self.assertEqual(second_balance.quantity_on_hand, 4)
        self.assertEqual(
            session.lines.get(variant=self.first_variant).difference_value,
            Decimal("-20.00"),
        )
        self.assertEqual(
            session.lines.get(variant=self.second_variant)
            .adjustment_movement.movement_type,
            StockMovement.Type.INVENTORY_GAIN,
        )

    def test_all_lines_must_be_counted(self):
        session = self.create_session()
        start_inventory_count(session=session)
        record_inventory_count(
            line=session.lines.get(variant=self.first_variant),
            counted_quantity=5,
            counted_by=self.user,
        )
        with self.assertRaises(ValidationError):
            confirm_inventory_count(session=session, confirmed_by=self.user)
        session.refresh_from_db()
        self.assertEqual(session.status, InventoryCountSession.Status.IN_PROGRESS)

    def test_changed_stock_blocks_confirmation(self):
        session = self.create_session()
        start_inventory_count(session=session)
        for line in session.lines.all():
            record_inventory_count(
                line=line,
                counted_quantity=line.expected_quantity,
                counted_by=self.user,
            )
        post_stock_movement(
            variant=self.first_variant,
            location=self.location,
            movement_type=StockMovement.Type.SALE,
            quantity_delta=-1,
        )
        with self.assertRaises(ValidationError):
            confirm_inventory_count(session=session, confirmed_by=self.user)

    def test_confirmed_inventory_cannot_be_changed_or_confirmed_twice(self):
        session = self.create_session()
        start_inventory_count(session=session)
        for line in session.lines.all():
            record_inventory_count(
                line=line,
                counted_quantity=line.expected_quantity,
                counted_by=self.user,
            )
        confirm_inventory_count(session=session, confirmed_by=self.user)
        line = InventoryCountLine.objects.filter(session=session).first()
        with self.assertRaises(ValidationError):
            record_inventory_count(
                line=line,
                counted_quantity=0,
                counted_by=self.user,
            )
        with self.assertRaises(ValidationError):
            confirm_inventory_count(session=session, confirmed_by=self.user)
