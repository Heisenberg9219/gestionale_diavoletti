from django.test import TestCase
from rest_framework.test import APIClient

from .models import Sale, SaleDraftChange
from . import tests as fixtures
from .services import set_sale_total_override
from vouchers.services import issue_voucher, redeem_voucher, get_voucher_ledger_balance


class DraftApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.SalesServiceTests.setUpTestData.__func__(cls)
        cls.user.is_superuser = True
        cls.user.save()

    create_sale = fixtures.SalesServiceTests.create_sale
    add_standard_line = fixtures.SalesServiceTests.add_standard_line

    def setUp(self):
        fixtures.SalesServiceTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.sale = self.create_sale()
        self.line = self.add_standard_line(sale=self.sale)

    def post(self, action, data):
        return self.client.post(f"/api/v1/sales/sales/{self.sale.pk}/{action}/", data, format="json")

    def test_remove_line_clears_total_and_records_audit(self):
        result = self.post("remove-line", {"line": str(self.line.pk), "reason": "Errore"})
        self.assertEqual(result.status_code, 200, result.data)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.final_total_amount, 0)
        self.assertTrue(SaleDraftChange.objects.filter(sale=self.sale, operation="REMOVE_LINE").exists())

    def test_remove_line_after_override(self):
        set_sale_total_override(sale=self.sale, final_total_amount="20.00", manual_override_reason="Arrotondamento", manual_override_by=self.user)
        result = self.post("remove-line", {"line": str(self.line.pk), "reason": "Errore"})
        self.assertEqual(result.status_code, 200, result.data)
        self.sale.refresh_from_db()
        self.assertIsNone(self.sale.manual_total_override_amount)
        self.assertEqual(self.sale.final_total_amount, 0)

    def test_remove_voucher_payment_restores_ledger_once(self):
        voucher = issue_voucher(voucher_type="GIFT_CARD", initial_amount="10.00", issued_by=self.user)
        movement, payment = redeem_voucher(voucher=voucher, sale=self.sale, requested_amount="10.00", created_by=self.user)
        payload = {"payment": str(payment.pk), "reason": "Cambio pagamento"}
        result = self.post("remove-payment", payload)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(get_voucher_ledger_balance(voucher=voucher), 10)
        self.assertEqual(self.post("remove-payment", payload).status_code, 404)
        self.assertEqual(get_voucher_ledger_balance(voucher=voucher), 10)

    def test_cancel_requires_payments_to_be_removed(self):
        self.assertEqual(self.post("add-payment", {"method": "CASH", "amount": "10.00", "cash_received_amount": "10.00"}).status_code, 201)
        self.assertEqual(self.post("cancel", {"reason": "Errore"}).status_code, 400)

    def test_cancel_open_sale(self):
        self.assertEqual(self.post("cancel", {"reason": "Cliente rinuncia"}).status_code, 200)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.CANCELLED)
        self.assertEqual(self.post("remove-line", {"line": str(self.line.pk), "reason": "Errore"}).status_code, 400)

    def test_cannot_forge_voucher_payment(self):
        self.assertEqual(self.post("add-payment", {"method": "GIFT_CARD", "amount": "10.00"}).status_code, 400)
