from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product, ProductVariant, Size, SizeScale
from core.models import Location, TaxRate
from inventory.models import StockBalance, VariantInventoryCost
from pricing.models import VariantSalePrice

from .models import CashRegister, Sale, SaleLine, SalePayment
from .services import (
    add_sale_payment,
    confirm_sale,
    get_open_sale_stock_warning,
    open_cash_session,
    set_sale_line,
    set_sale_total_override,
)


class SalesServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="sales-test@example.com",
            password="test-password",
        )
        cls.tax_rate = TaxRate.objects.create(
            code="SALES_TEST_VAT",
            name="IVA test vendite",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="SALES_TEST_CATEGORY",
            name="Categoria test vendite",
        )
        size_scale = SizeScale.objects.create(
            code="SALES_TEST_SCALE",
            name="Scala test vendite",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=size_scale,
            code="SALES_TEST_SIZE",
            label="Taglia unica test",
        )
        product = Product.objects.create(
            code="SALES_TEST_PRODUCT",
            name="Prodotto test vendite",
            category=category,
            tax_rate=cls.tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="SALES_TEST_SKU",
            size=size,
        )
        cls.location = Location.objects.create(
            code="SALES_TEST_LOCATION",
            name="Negozio test vendite",
            type=Location.Type.SALES_FLOOR,
        )
        cls.cash_register = CashRegister.objects.create(
            code="SALES_TEST_REGISTER",
            name="Cassa test vendite",
            location=cls.location,
        )
        VariantSalePrice.objects.create(
            variant=cls.variant,
            amount="24.90",
            created_by=cls.user,
        )

    def setUp(self):
        StockBalance.objects.update_or_create(
            variant=self.variant,
            location=self.location,
            defaults={"quantity_on_hand": 10},
        )
        VariantInventoryCost.objects.update_or_create(
            variant=self.variant,
            defaults={
                "weighted_average_unit_cost": Decimal("10.0000"),
                "total_quantity": 10,
                "inventory_value": Decimal("100.00"),
            },
        )

    def create_sale(self):
        cash_session = open_cash_session(
            cash_register=self.cash_register,
            opened_by=self.user,
            opening_cash_amount="100.00",
        )
        return Sale.objects.create(
            cash_session=cash_session,
            location=self.location,
            opened_by=self.user,
        )

    def add_standard_line(self, *, sale, quantity=1):
        return set_sale_line(
            sale=sale,
            variant=self.variant,
            quantity=quantity,
        )

    def test_manual_line_price_is_recorded(self):
        sale = self.create_sale()
        line = set_sale_line(
            sale=sale,
            variant=self.variant,
            quantity=1,
            manual_unit_price="24.00",
            manual_override_reason="Arrotondamento richiesto",
            manual_override_by=self.user,
        )

        sale.refresh_from_db()
        self.assertEqual(line.base_unit_price, Decimal("24.90"))
        self.assertEqual(line.final_unit_price, Decimal("24.00"))
        self.assertEqual(line.manual_adjustment, Decimal("-0.90"))
        self.assertEqual(sale.final_total_amount, Decimal("24.00"))

    def test_total_override_is_distributed_and_can_be_removed(self):
        sale = self.create_sale()
        line = self.add_standard_line(sale=sale, quantity=2)

        set_sale_total_override(
            sale=sale,
            final_total_amount="48.90",
            manual_override_reason="Arrotondamento totale",
            manual_override_by=self.user,
        )

        sale.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(sale.calculated_total_amount, Decimal("49.80"))
        self.assertEqual(sale.final_total_amount, Decimal("48.90"))
        self.assertEqual(line.total_override_share, Decimal("-0.90"))
        self.assertEqual(line.net_amount, Decimal("48.90"))

        set_sale_total_override(
            sale=sale,
            final_total_amount="49.80",
            manual_override_reason="",
            manual_override_by=self.user,
        )

        sale.refresh_from_db()
        line.refresh_from_db()
        self.assertIsNone(sale.manual_total_override_amount)
        self.assertEqual(line.total_override_share, Decimal("0.00"))
        self.assertEqual(line.net_amount, Decimal("49.80"))

    def test_total_reduction_is_rejected_for_sale_price_mode(self):
        sale = self.create_sale()
        line = self.add_standard_line(sale=sale)
        line.pricing_mode = SaleLine.PricingMode.SALE
        line.save(update_fields=("pricing_mode", "updated_at"))

        with self.assertRaises(ValidationError):
            set_sale_total_override(
                sale=sale,
                final_total_amount="24.00",
                manual_override_reason="Sconto aggiuntivo",
                manual_override_by=self.user,
            )

    def test_open_sales_generate_stock_warning(self):
        StockBalance.objects.filter(
            variant=self.variant,
            location=self.location,
        ).update(quantity_on_hand=1)
        first_sale = self.create_sale()
        self.add_standard_line(sale=first_sale)
        second_sale = Sale.objects.create(
            cash_session=first_sale.cash_session,
            location=self.location,
            opened_by=self.user,
        )
        self.add_standard_line(sale=second_sale)

        warning = get_open_sale_stock_warning(
            variant=self.variant,
            location=self.location,
        )

        self.assertEqual(warning["available_quantity"], 1)
        self.assertEqual(warning["open_sale_quantity"], 2)
        self.assertTrue(warning["has_insufficient_stock_warning"])

    def test_cash_payment_calculates_change(self):
        sale = self.create_sale()
        self.add_standard_line(sale=sale)
        sale.refresh_from_db()

        payment = add_sale_payment(
            sale=sale,
            method=SalePayment.Method.CASH,
            amount="24.90",
            cash_received_amount="30.00",
            created_by=self.user,
        )

        self.assertEqual(payment.amount, Decimal("24.90"))
        self.assertEqual(payment.cash_change_amount, Decimal("5.10"))

    def test_mixed_payments_cannot_exceed_sale_total(self):
        sale = self.create_sale()
        self.add_standard_line(sale=sale)
        sale.refresh_from_db()
        add_sale_payment(
            sale=sale,
            method=SalePayment.Method.CARD,
            amount="10.00",
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            add_sale_payment(
                sale=sale,
                method=SalePayment.Method.CASH,
                amount="15.00",
                cash_received_amount="20.00",
                created_by=self.user,
            )

    def test_confirmation_reduces_stock_and_assigns_number(self):
        sale = self.create_sale()
        self.add_standard_line(sale=sale, quantity=2)
        sale.refresh_from_db()
        add_sale_payment(
            sale=sale,
            method=SalePayment.Method.CARD,
            amount="49.80",
            created_by=self.user,
        )

        confirm_sale(sale=sale, confirmed_by=self.user)

        sale.refresh_from_db()
        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        )
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertRegex(sale.number, r"^V-\d{4}-000001$")
        self.assertEqual(balance.quantity_on_hand, 8)
        self.assertEqual(sale.total_cost_amount, Decimal("20.00"))

    def test_insufficient_stock_rolls_back_confirmation(self):
        StockBalance.objects.filter(
            variant=self.variant,
            location=self.location,
        ).update(quantity_on_hand=1)
        sale = self.create_sale()
        self.add_standard_line(sale=sale, quantity=2)
        sale.refresh_from_db()
        add_sale_payment(
            sale=sale,
            method=SalePayment.Method.CARD,
            amount="49.80",
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            confirm_sale(sale=sale, confirmed_by=self.user)

        sale.refresh_from_db()
        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        )
        self.assertEqual(sale.status, Sale.Status.OPEN)
        self.assertEqual(sale.number, "")
        self.assertEqual(balance.quantity_on_hand, 1)
