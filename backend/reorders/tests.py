from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product, ProductVariant, Size, SizeScale
from core.models import Location, TaxRate
from inventory.models import StockBalance
from notifications.models import Notification
from notifications.services import create_notification
from purchasing.models import PurchaseOrder, PurchaseOrderLine
from suppliers.models import Supplier, SupplierVariant

from .models import ReorderItem
from .services import (
    add_to_reorder_list,
    complete_reorder,
    get_pending_reorders_by_supplier,
    link_reorder_to_purchase_order,
    remove_from_reorder_list,
    update_pending_reorder,
)


class ReorderServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="reorders-test@example.com",
            password="test-password",
        )
        cls.location = Location.objects.create(
            code="REORDER_LOCATION",
            name="Negozio test riordini",
            type=Location.Type.SALES_FLOOR,
        )
        tax_rate = TaxRate.objects.create(
            code="REORDER_VAT",
            name="IVA test riordini",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="REORDER_CATEGORY",
            name="Categoria test riordini",
        )
        scale = SizeScale.objects.create(
            code="REORDER_SCALE",
            name="Scala test riordini",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=scale,
            code="REORDER_SIZE",
            label="Taglia unica",
        )
        second_size = Size.objects.create(
            size_scale=scale,
            code="REORDER_SECOND_SIZE",
            label="Seconda taglia test",
        )
        product = Product.objects.create(
            code="REORDER_PRODUCT",
            name="Prodotto test riordini",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="REORDER_SKU",
            size=size,
        )
        cls.unassigned_variant = ProductVariant.objects.create(
            product=product,
            sku="REORDER_NO_SUPPLIER_SKU",
            size=second_size,
            color=None,
        )
        cls.supplier = Supplier.objects.create(
            code="REORDER_SUPPLIER",
            business_name="Fornitore riordini",
        )
        cls.other_supplier = Supplier.objects.create(
            code="REORDER_OTHER_SUPPLIER",
            business_name="Altro fornitore",
        )
        SupplierVariant.objects.create(
            supplier=cls.supplier,
            variant=cls.variant,
            is_preferred=True,
            minimum_order_quantity=2,
        )
        SupplierVariant.objects.create(
            supplier=cls.other_supplier,
            variant=cls.variant,
        )

    def setUp(self):
        self.balance = StockBalance.objects.create(
            variant=self.variant,
            location=self.location,
            quantity_on_hand=0,
        )

    def test_preferred_supplier_and_minimum_quantity_are_suggested(self):
        item, created = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        self.assertTrue(created)
        self.assertEqual(item.supplier, self.supplier)
        self.assertEqual(item.requested_quantity, 2)
        self.assertEqual(item.reason, "Articolo esaurito")

    def test_pending_item_is_not_duplicated(self):
        first, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        second, created = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ReorderItem.objects.count(), 1)

    def test_stock_notification_is_linked_and_resolved(self):
        notification, _ = create_notification(
            notification_type=Notification.Type.STOCK_DEPLETED,
            priority=Notification.Priority.HIGH,
            title="Articolo esaurito",
            message="Aggiungere al riordino?",
            deduplication_key=f"reorder-test:{self.balance.pk}",
            users=(self.user,),
            source_type="inventory.StockBalance",
            source_id=self.balance.pk,
        )
        item, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
            source_notification=notification,
        )
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.RESOLVED)
        self.assertEqual(item.notification_links.get().notification, notification)

    def test_update_is_traced(self):
        item, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        update_pending_reorder(
            reorder_item=item,
            requested_quantity=4,
            supplier=self.other_supplier,
            updated_by=self.user,
        )
        item.refresh_from_db()
        change = item.changes.get()
        self.assertEqual(change.previous_quantity, 2)
        self.assertEqual(change.new_quantity, 4)
        self.assertEqual(change.new_supplier, self.other_supplier)

    def test_removed_item_disappears_and_can_be_added_again(self):
        item, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        remove_from_reorder_list(
            reorder_item=item,
            removed_by=self.user,
            reason="Non più necessario",
        )
        replacement, created = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        self.assertTrue(created)
        self.assertNotEqual(item.pk, replacement.pk)
        self.assertEqual(
            ReorderItem.objects.filter(status=ReorderItem.Status.PENDING).count(),
            1,
        )

    def test_pending_items_are_grouped_by_supplier_and_unassigned(self):
        add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        add_to_reorder_list(
            variant=self.unassigned_variant,
            location=self.location,
            added_by=self.user,
        )
        groups = get_pending_reorders_by_supplier()
        self.assertEqual(len(groups), 2)
        self.assertEqual(
            {group["supplier"] for group in groups},
            {self.supplier, None},
        )

    def test_reorder_can_be_linked_to_purchase_order_and_completed(self):
        item, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
        )
        order = PurchaseOrder.objects.create(
            number="PO-REORDER-001",
            supplier=self.supplier,
            created_by=self.user,
        )
        order_line = PurchaseOrderLine.objects.create(
            order=order,
            variant=self.variant,
            quantity_ordered=2,
        )
        link_reorder_to_purchase_order(
            reorder_item=item,
            purchase_order_line=order_line,
            ordered_by=self.user,
        )
        item.refresh_from_db()
        self.assertEqual(item.status, ReorderItem.Status.ORDERED)

        complete_reorder(reorder_item=item, completed_by=self.user)
        item.refresh_from_db()
        self.assertEqual(item.status, ReorderItem.Status.COMPLETED)

    def test_order_quantity_cannot_be_lower_than_requested(self):
        item, _ = add_to_reorder_list(
            variant=self.variant,
            location=self.location,
            added_by=self.user,
            requested_quantity=3,
        )
        order = PurchaseOrder.objects.create(
            number="PO-REORDER-002",
            supplier=self.supplier,
            created_by=self.user,
        )
        order_line = PurchaseOrderLine.objects.create(
            order=order,
            variant=self.variant,
            quantity_ordered=2,
        )
        with self.assertRaises(ValidationError):
            link_reorder_to_purchase_order(
                reorder_item=item,
                purchase_order_line=order_line,
                ordered_by=self.user,
            )
