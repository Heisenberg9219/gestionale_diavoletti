from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from catalog.models import (
    Category,
    Product,
    ProductVariant,
    Size,
    SizeScale,
)
from core.models import Location, TaxRate
from inventory.models import StockBalance, StockMovement, VariantInventoryCost
from inventory.services import post_stock_movement
from pricing.models import VariantSalePrice
from suppliers.models import Supplier

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseCostAdjustment,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierInvoice,
    SupplierInvoiceLine,
    SupplierInvoiceReceipt,
)
from .services import (
    confirm_goods_receipt,
    confirm_supplier_invoice,
    send_purchase_order,
)


class PurchasingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(
            code="PURCH_TEST_VAT",
            name="IVA test acquisti",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="PURCH_TEST_CATEGORY",
            name="Categoria test acquisti",
        )
        size_scale = SizeScale.objects.create(
            code="PURCH_TEST_SCALE",
            name="Scala test acquisti",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="PURCH_TEST_SIZE",
            label="Taglia unica test",
        )
        product = Product.objects.create(
            code="PURCH_TEST_PRODUCT",
            name="Prodotto test acquisti",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="PURCH_TEST_SKU",
            size=size,
        )
        cls.supplier = Supplier.objects.create(
            code="PURCH_TEST_SUPPLIER",
            business_name="Fornitore test acquisti",
        )
        cls.other_supplier = Supplier.objects.create(
            code="PURCH_TEST_OTHER_SUPPLIER",
            business_name="Altro fornitore test",
        )
        cls.location = Location.objects.create(
            code="PURCH_TEST_LOCATION",
            name="Ubicazione test acquisti",
            type=Location.Type.OTHER,
        )

    def create_order(self, *, number="PO-TEST", quantity=10):
        order = PurchaseOrder.objects.create(
            number=number,
            supplier=self.supplier,
        )
        line = PurchaseOrderLine.objects.create(
            order=order,
            variant=self.variant,
            quantity_ordered=quantity,
            expected_unit_cost="10.0000",
        )
        return order, line

    def create_receipt(
        self,
        *,
        number="GR-TEST",
        supplier=None,
        order=None,
        order_line=None,
        quantity=10,
        unit_cost="10.0000",
        final_sale_price=None,
    ):
        receipt = GoodsReceipt.objects.create(
            number=number,
            supplier=supplier or self.supplier,
            purchase_order=order,
            destination_location=self.location,
        )
        line = GoodsReceiptLine.objects.create(
            receipt=receipt,
            variant=self.variant,
            purchase_order_line=order_line,
            quantity_received=quantity,
            unit_cost=unit_cost,
            final_sale_price=final_sale_price,
        )
        return receipt, line

    def test_order_with_lines_can_be_sent(self):
        order, _ = self.create_order()

        send_purchase_order(order=order)

        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.SENT)
        self.assertIsNotNone(order.sent_at)

    def test_receipt_updates_inventory_price_and_order(self):
        order, order_line = self.create_order(quantity=10)
        send_purchase_order(order=order)

        receipt, _ = self.create_receipt(
            order=order,
            order_line=order_line,
            quantity=10,
            unit_cost="10.0000",
            final_sale_price="24.90",
        )
        confirm_goods_receipt(receipt=receipt)

        receipt.refresh_from_db()
        order.refresh_from_db()

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        )
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )
        current_price = VariantSalePrice.objects.get(
            variant=self.variant,
            valid_until__isnull=True,
        )

        self.assertEqual(receipt.status, GoodsReceipt.Status.CONFIRMED)
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(balance.quantity_on_hand, 10)
        self.assertEqual(inventory_cost.total_quantity, 10)
        self.assertEqual(
            inventory_cost.weighted_average_unit_cost,
            Decimal("10.0000"),
        )
        self.assertEqual(current_price.amount, Decimal("24.90"))

    def test_receipt_without_purchase_order_is_allowed(self):
        receipt, _ = self.create_receipt(
            number="GR-WITHOUT-ORDER",
            quantity=3,
            unit_cost=None,
        )

        confirm_goods_receipt(receipt=receipt)

        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        )
        self.assertEqual(balance.quantity_on_hand, 3)

    def test_supplier_mismatch_rolls_back_receipt(self):
        order, order_line = self.create_order()
        send_purchase_order(order=order)

        receipt, _ = self.create_receipt(
            number="GR-WRONG-SUPPLIER",
            supplier=self.other_supplier,
            order=order,
            order_line=order_line,
        )

        with self.assertRaises(ValidationError):
            confirm_goods_receipt(receipt=receipt)

        receipt.refresh_from_db()
        self.assertEqual(receipt.status, GoodsReceipt.Status.DRAFT)
        self.assertFalse(
            StockMovement.objects.filter(
                source_id=receipt.id,
            ).exists()
        )

    def test_invoice_adjustment_is_split_between_stock_and_sold(self):
        receipt, receipt_line = self.create_receipt(
            number="GR-INVOICE-TEST",
            quantity=10,
            unit_cost="10.0000",
        )
        confirm_goods_receipt(receipt=receipt)

        post_stock_movement(
            variant=self.variant,
            location=self.location,
            movement_type=StockMovement.Type.SALE,
            quantity_delta=-6,
        )

        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-TEST-001",
            invoice_date=timezone.localdate(),
            taxable_amount="98.36",
            tax_amount="21.64",
            total_amount="120.00",
        )
        SupplierInvoiceReceipt.objects.create(
            invoice=invoice,
            receipt=receipt,
        )
        SupplierInvoiceLine.objects.create(
            invoice=invoice,
            variant=self.variant,
            receipt_line=receipt_line,
            quantity_invoiced=10,
            final_unit_cost="12.0000",
            tax_percentage="22.00",
            taxable_amount="98.36",
            tax_amount="21.64",
            total_amount="120.00",
        )

        confirm_supplier_invoice(invoice=invoice)

        invoice.refresh_from_db()
        inventory_cost = VariantInventoryCost.objects.get(
            variant=self.variant,
        )
        adjustment = PurchaseCostAdjustment.objects.get(
            invoice_line__invoice=invoice,
        )

        self.assertEqual(
            invoice.status,
            SupplierInvoice.Status.CONFIRMED,
        )
        self.assertEqual(adjustment.total_cost_delta, Decimal("20.00"))
        self.assertEqual(adjustment.remaining_quantity_affected, 4)
        self.assertEqual(
            adjustment.inventory_value_delta,
            Decimal("8.00"),
        )
        self.assertEqual(adjustment.sold_quantity_affected, 6)
        self.assertEqual(
            adjustment.sold_cost_delta,
            Decimal("12.00"),
        )
        self.assertEqual(
            inventory_cost.inventory_value,
            Decimal("48.00"),
        )
        self.assertEqual(
            inventory_cost.weighted_average_unit_cost,
            Decimal("12.0000"),
        )

    def test_invoice_totals_mismatch_rolls_back_confirmation(self):
        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-WRONG-TOTAL",
            invoice_date=timezone.localdate(),
            taxable_amount="100.00",
            tax_amount="20.00",
            total_amount="120.00",
        )
        SupplierInvoiceLine.objects.create(
            invoice=invoice,
            variant=self.variant,
            quantity_invoiced=1,
            final_unit_cost="108.0000",
            tax_percentage="20.00",
            taxable_amount="90.00",
            tax_amount="18.00",
            total_amount="108.00",
        )

        with self.assertRaises(ValidationError):
            confirm_supplier_invoice(invoice=invoice)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SupplierInvoice.Status.DRAFT)
        self.assertFalse(
            PurchaseCostAdjustment.objects.filter(
                invoice_line__invoice=invoice,
            ).exists()
        )