from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Location, ShopSettings
from sales.models import Sale, SalePayment

from .models import Voucher, VoucherMovement
from .services import (
    authorize_expired_voucher,
    cancel_voucher,
    change_voucher_expiry,
    get_voucher_ledger_balance,
    issue_voucher,
    redeem_voucher,
)


class VoucherServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="voucher-test@example.com",
            password="test-password",
        )
        cls.location = Location.objects.create(
            code="VOUCHER_TEST_LOCATION",
            name="Negozio test buoni",
            type=Location.Type.SALES_FLOOR,
        )
        ShopSettings.objects.update_or_create(
            singleton_key=True,
            defaults={
                "shop_name": "I Diavoletti",
                "voucher_validity_months": 6,
            },
        )

    def create_sale(self, total="40.00"):
        return Sale.objects.create(
            location=self.location,
            opened_by=self.user,
            subtotal_amount=total,
            calculated_total_amount=total,
            final_total_amount=total,
        )

    def create_voucher(self, amount="30.00", **kwargs):
        return issue_voucher(
            voucher_type=Voucher.Type.GIFT_CARD,
            initial_amount=amount,
            issued_by=self.user,
            **kwargs,
        )

    def test_issue_uses_six_month_expiry_and_ledger(self):
        issued_at = timezone.now().replace(microsecond=0)
        voucher = self.create_voucher(
            issued_at=issued_at,
            holder_first_name="Mario",
            holder_last_name="Rossi",
        )

        expected_month = (issued_at.month + 5) % 12 + 1
        self.assertEqual(voucher.expires_at.month, expected_month)
        self.assertEqual(voucher.current_balance, Decimal("30.00"))
        self.assertEqual(
            get_voucher_ledger_balance(voucher=voucher),
            Decimal("30.00"),
        )
        self.assertEqual(
            voucher.movements.get().movement_type,
            VoucherMovement.Type.ISSUE,
        )

    def test_partial_redemption_keeps_residual_balance(self):
        voucher = self.create_voucher(amount="50.00")
        sale = self.create_sale(total="30.00")

        movement, payment = redeem_voucher(
            voucher=voucher,
            sale=sale,
            requested_amount="20.00",
            created_by=self.user,
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.current_balance, Decimal("30.00"))
        self.assertEqual(voucher.status, Voucher.Status.ACTIVE)
        self.assertEqual(movement.amount_delta, Decimal("-20.00"))
        self.assertEqual(payment.method, SalePayment.Method.GIFT_CARD)
        self.assertEqual(payment.amount, Decimal("20.00"))

    def test_smaller_voucher_is_exhausted(self):
        voucher = self.create_voucher(amount="15.00")
        sale = self.create_sale(total="40.00")

        redeem_voucher(
            voucher=voucher,
            sale=sale,
            requested_amount="40.00",
            created_by=self.user,
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.current_balance, Decimal("0.00"))
        self.assertEqual(voucher.status, Voucher.Status.EXHAUSTED)
        self.assertEqual(sale.payments.get().amount, Decimal("15.00"))

    def test_expired_voucher_requires_authorization(self):
        now = timezone.now()
        voucher = self.create_voucher(
            issued_at=now - timedelta(days=200),
            expires_at=now - timedelta(days=1),
        )
        sale = self.create_sale()

        with self.assertRaises(ValidationError):
            redeem_voucher(
                voucher=voucher,
                sale=sale,
                requested_amount="10.00",
                created_by=self.user,
                occurred_at=now,
            )

        authorization = authorize_expired_voucher(
            voucher=voucher,
            sale=sale,
            reason="Eccezione autorizzata dal titolare",
            authorized_by=self.user,
            authorized_at=now,
        )
        redeem_voucher(
            voucher=voucher,
            sale=sale,
            requested_amount="10.00",
            created_by=self.user,
            expired_authorization=authorization,
            occurred_at=now,
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.current_balance, Decimal("20.00"))

    def test_expiry_change_is_traced(self):
        voucher = self.create_voucher()
        old_expiry = voucher.expires_at
        new_expiry = old_expiry + timedelta(days=30)

        change = change_voucher_expiry(
            voucher=voucher,
            new_expires_at=new_expiry,
            reason="Proroga concordata",
            changed_by=self.user,
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.expires_at, new_expiry)
        self.assertEqual(change.previous_expires_at, old_expiry)

    def test_cancellation_zeroes_balance_and_creates_movement(self):
        voucher = self.create_voucher()

        cancel_voucher(
            voucher=voucher,
            cancelled_by=self.user,
            reason="Buono emesso per errore",
        )

        voucher.refresh_from_db()
        self.assertEqual(voucher.status, Voucher.Status.CANCELLED)
        self.assertEqual(voucher.current_balance, Decimal("0.00"))
        self.assertEqual(voucher.movements.count(), 2)

    def test_movements_cannot_be_changed_or_deleted(self):
        voucher = self.create_voucher()
        movement = voucher.movements.get()
        movement.notes = "Modifica non consentita"

        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()
