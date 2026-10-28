from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductVariant, Size, SizeScale
from core.models import Location, ShopSettings, TaxRate
from customers.models import Customer
from inventory.models import StockBalance, VariantInventoryCost
from loyalty.models import LoyaltyPointMovement
from loyalty.services import get_customer_points_balance, record_point_movement
from sales.models import Sale, SaleLine
from accounts.models import UserPagePermission
from vouchers.models import Voucher, VoucherMovement

from .models import CustomerReturn
from .services import (
    cancel_confirmed_return,
    confirm_customer_return,
    create_customer_return,
    get_returnable_quantity,
    set_return_line,
)


class CustomerReturnServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="returns-test@example.com",
            password="test-password",
        )
        cls.customer = Customer.objects.create(
            customer_code="RETURN_CUSTOMER",
            first_name="Mario",
            last_name="Rossi",
            created_by=cls.user,
        )
        cls.location = Location.objects.create(
            code="RETURN_LOCATION",
            name="Negozio test resi",
            type=Location.Type.SALES_FLOOR,
        )
        tax_rate = TaxRate.objects.create(
            code="RETURN_VAT",
            name="IVA test resi",
            percentage="22.00",
        )
        category = Category.objects.create(
            code="RETURN_CATEGORY",
            name="Categoria test resi",
        )
        scale = SizeScale.objects.create(
            code="RETURN_SCALE",
            name="Scala test resi",
            scale_type=SizeScale.Type.ONE_SIZE,
        )
        size = Size.objects.create(
            size_scale=scale,
            code="RETURN_SIZE",
            label="Taglia unica",
        )
        product = Product.objects.create(
            code="RETURN_PRODUCT",
            name="Prodotto test resi",
            category=category,
            tax_rate=tax_rate,
        )
        cls.variant = ProductVariant.objects.create(
            product=product,
            sku="RETURN_SKU",
            size=size,
        )
        ShopSettings.objects.update_or_create(
            singleton_key=True,
            defaults={
                "shop_name": "I Diavoletti",
                "return_credit_months": 6,
            },
        )

    def setUp(self):
        self.sale = Sale.objects.create(
            number="SALE-RETURN-TEST",
            customer=self.customer,
            location=self.location,
            status=Sale.Status.CONFIRMED,
            opened_by=self.user,
            confirmed_by=self.user,
            subtotal_amount="49.80",
            calculated_total_amount="49.80",
            final_total_amount="49.80",
        )
        self.sale_line = SaleLine.objects.create(
            sale=self.sale,
            variant=self.variant,
            quantity=2,
            sku_snapshot=self.variant.sku,
            product_name_snapshot=self.variant.product.name,
            size_snapshot=self.variant.size.label,
            base_unit_price="24.90",
            final_unit_price="24.90",
            gross_amount="49.80",
            net_amount="49.80",
            tax_percentage="22.00",
            tax_amount="8.98",
            unit_cost_snapshot="10.0000",
            total_cost_amount="20.00",
        )
        StockBalance.objects.update_or_create(
            variant=self.variant,
            location=self.location,
            defaults={"quantity_on_hand": 0},
        )
        VariantInventoryCost.objects.update_or_create(
            variant=self.variant,
            defaults={
                "weighted_average_unit_cost": Decimal("10.0000"),
                "total_quantity": 0,
                "inventory_value": Decimal("0.00"),
            },
        )
        record_point_movement(
            customer=self.customer,
            points_delta=4,
            movement_type=LoyaltyPointMovement.Type.MANUAL_ADJUSTMENT,
            source_type="sales.Sale",
            source_id=self.sale.id,
            created_by=self.user,
        )
        LoyaltyPointMovement.objects.filter(
            source_id=self.sale.id
        ).update(movement_type=LoyaltyPointMovement.Type.EARNED)

    def create_draft_return(self):
        return create_customer_return(
            original_sale=self.sale,
            reason="Taglia non adatta",
            created_by=self.user,
        )

    def test_return_requires_confirmed_sale(self):
        self.sale.status = Sale.Status.OPEN
        self.sale.number = ""
        self.sale.save(update_fields=("status", "number", "updated_at"))
        with self.assertRaises(ValidationError):
            create_customer_return(
                original_sale=self.sale,
                reason="Tentativo non valido",
                created_by=self.user,
            )

    def test_partial_return_creates_voucher_stock_and_points_reversal(self):
        customer_return = self.create_draft_return()
        set_return_line(
            customer_return=customer_return,
            original_sale_line=self.sale_line,
            quantity=1,
            restock=True,
        )
        result = confirm_customer_return(
            customer_return=customer_return,
            confirmed_by=self.user,
        )

        self.assertEqual(result.status, CustomerReturn.Status.CONFIRMED)
        self.assertEqual(result.total_refund_amount, Decimal("24.90"))
        self.assertEqual(result.points_reversed, 2)
        self.assertEqual(result.return_voucher.voucher_type, Voucher.Type.RETURN_CREDIT)
        self.assertEqual(result.return_voucher.current_balance, Decimal("24.90"))
        self.assertEqual(
            StockBalance.objects.get(
                variant=self.variant,
                location=self.location,
            ).quantity_on_hand,
            1,
        )
        self.assertEqual(get_customer_points_balance(customer=self.customer), 2)

    def test_second_return_only_uses_remaining_quantity_and_points(self):
        first = self.create_draft_return()
        set_return_line(
            customer_return=first,
            original_sale_line=self.sale_line,
            quantity=1,
        )
        confirm_customer_return(customer_return=first, confirmed_by=self.user)

        second = self.create_draft_return()
        set_return_line(
            customer_return=second,
            original_sale_line=self.sale_line,
            quantity=1,
        )
        result = confirm_customer_return(
            customer_return=second,
            confirmed_by=self.user,
        )

        self.assertEqual(result.total_refund_amount, Decimal("24.90"))
        self.assertEqual(result.points_reversed, 2)
        self.assertEqual(get_returnable_quantity(original_sale_line=self.sale_line), 0)
        self.assertEqual(get_customer_points_balance(customer=self.customer), 0)

    def test_already_returned_quantity_cannot_be_returned_again(self):
        first = self.create_draft_return()
        set_return_line(
            customer_return=first,
            original_sale_line=self.sale_line,
            quantity=2,
        )
        confirm_customer_return(customer_return=first, confirmed_by=self.user)

        second = self.create_draft_return()
        with self.assertRaises(ValidationError):
            set_return_line(
                customer_return=second,
                original_sale_line=self.sale_line,
                quantity=1,
            )

    def test_non_restocked_item_does_not_change_inventory(self):
        customer_return = self.create_draft_return()
        set_return_line(
            customer_return=customer_return,
            original_sale_line=self.sale_line,
            quantity=1,
            restock=False,
        )
        confirm_customer_return(
            customer_return=customer_return,
            confirmed_by=self.user,
        )
        balance = StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        )
        self.assertEqual(balance.quantity_on_hand, 0)

    def test_empty_return_cannot_be_confirmed(self):
        with self.assertRaises(ValidationError):
            confirm_customer_return(
                customer_return=self.create_draft_return(),
                confirmed_by=self.user,
            )

    def test_return_voucher_uses_configured_six_month_validity(self):
        customer_return = self.create_draft_return()
        set_return_line(
            customer_return=customer_return,
            original_sale_line=self.sale_line,
            quantity=1,
        )
        result = confirm_customer_return(
            customer_return=customer_return,
            confirmed_by=self.user,
        )
        issued = result.return_voucher.issued_at
        expected_month = (issued.month + 5) % 12 + 1
        self.assertEqual(result.return_voucher.expires_at.month, expected_month)

    # ---------- Annullamento di un reso confermato ----------

    def confirmed_return(self, quantity=1):
        customer_return = self.create_draft_return()
        set_return_line(
            customer_return=customer_return,
            original_sale_line=self.sale_line,
            quantity=quantity,
        )
        return confirm_customer_return(
            customer_return=customer_return,
            confirmed_by=self.user,
        )

    def stock(self):
        return StockBalance.objects.get(
            variant=self.variant,
            location=self.location,
        ).quantity_on_hand

    def test_cancel_confirmed_return_reverts_stock_voucher_and_points(self):
        confirmed = self.confirmed_return()
        self.assertEqual(self.stock(), 1)
        self.assertEqual(get_customer_points_balance(customer=self.customer), 2)

        result = cancel_confirmed_return(
            customer_return=confirmed,
            cancelled_by=self.user,
            reason="Reso registrato per errore",
        )

        self.assertEqual(result.status, CustomerReturn.Status.CANCELLED)
        self.assertEqual(result.number, confirmed.number)
        self.assertEqual(result.cancellation_reason, "Reso registrato per errore")
        voucher = Voucher.objects.get(pk=confirmed.return_voucher_id)
        self.assertEqual(voucher.status, Voucher.Status.CANCELLED)
        self.assertEqual(voucher.current_balance, Decimal("0.00"))
        self.assertEqual(self.stock(), 0)
        self.assertEqual(get_customer_points_balance(customer=self.customer), 4)
        # L'articolo torna restituibile e non pesa più sul report dei resi.
        self.assertEqual(get_returnable_quantity(original_sale_line=self.sale_line), 2)

    def test_cancelled_return_allows_a_new_return_of_the_same_item(self):
        confirmed = self.confirmed_return(quantity=2)
        cancel_confirmed_return(
            customer_return=confirmed,
            cancelled_by=self.user,
            reason="Errore di taglia",
        )
        again = self.confirmed_return(quantity=2)
        self.assertEqual(again.status, CustomerReturn.Status.CONFIRMED)
        self.assertEqual(again.points_reversed, 4)
        self.assertEqual(self.stock(), 2)

    def test_cannot_cancel_return_when_voucher_was_used(self):
        confirmed = self.confirmed_return()
        voucher = confirmed.return_voucher
        VoucherMovement.objects.create(
            voucher=voucher,
            movement_type=VoucherMovement.Type.REDEMPTION,
            amount_delta=Decimal("-5.00"),
            balance_after=voucher.initial_amount - Decimal("5.00"),
            occurred_at=voucher.issued_at,
            created_by=self.user,
        )
        Voucher.objects.filter(pk=voucher.pk).update(
            current_balance=voucher.initial_amount - Decimal("5.00")
        )

        with self.assertRaises(ValidationError):
            cancel_confirmed_return(
                customer_return=confirmed,
                cancelled_by=self.user,
                reason="Tentativo",
            )
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, CustomerReturn.Status.CONFIRMED)
        self.assertEqual(self.stock(), 1)

    def test_cannot_cancel_return_when_item_was_sold_again(self):
        confirmed = self.confirmed_return()
        StockBalance.objects.filter(
            variant=self.variant,
            location=self.location,
        ).update(quantity_on_hand=0)

        with self.assertRaises(ValidationError):
            cancel_confirmed_return(
                customer_return=confirmed,
                cancelled_by=self.user,
                reason="Tentativo",
            )
        confirmed.refresh_from_db()
        voucher = Voucher.objects.get(pk=confirmed.return_voucher_id)
        self.assertEqual(confirmed.status, CustomerReturn.Status.CONFIRMED)
        self.assertEqual(voucher.status, Voucher.Status.ACTIVE)

    def test_cancel_confirmed_return_requires_reason_and_confirmed_status(self):
        confirmed = self.confirmed_return()
        with self.assertRaises(ValidationError):
            cancel_confirmed_return(
                customer_return=confirmed,
                cancelled_by=self.user,
                reason="  ",
            )
        with self.assertRaises(ValidationError):
            cancel_confirmed_return(
                customer_return=self.create_draft_return(),
                cancelled_by=self.user,
                reason="Bozza",
            )

    def test_api_cancel_confirmed_return_is_reserved_to_owner(self):
        confirmed = self.confirmed_return()
        url = f"/api/v1/returns/returns/{confirmed.id}/cancel/"
        clerk = get_user_model().objects.create_user(
            email="returns-clerk@example.com",
            password="test-password",
        )
        clerk.groups.add(Group.objects.get_or_create(name="Commesso")[0])
        UserPagePermission.objects.create(
            user=clerk,
            page_key="Resi",
            can_view=True,
            can_create=True,
            can_update=True,
            can_delete=True,
        )
        client = APIClient()
        client.force_authenticate(clerk)
        response = client.post(url, {"reason": "Errore"}, format="json")
        self.assertEqual(response.status_code, 403)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, CustomerReturn.Status.CONFIRMED)

        owner = get_user_model().objects.create_user(
            email="returns-owner@example.com",
            password="test-password",
        )
        owner.groups.add(Group.objects.get_or_create(name="Titolare")[0])
        client.force_authenticate(owner)
        response = client.post(url, {"reason": "Errore"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], CustomerReturn.Status.CANCELLED)

    def test_api_cancel_still_cancels_drafts(self):
        draft = self.create_draft_return()
        owner = get_user_model().objects.create_user(
            email="returns-owner-draft@example.com",
            password="test-password",
        )
        owner.groups.add(Group.objects.get_or_create(name="Titolare")[0])
        client = APIClient()
        client.force_authenticate(owner)
        response = client.post(
            f"/api/v1/returns/returns/{draft.id}/cancel/",
            {"reason": "Bozza non necessaria"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], CustomerReturn.Status.CANCELLED)
