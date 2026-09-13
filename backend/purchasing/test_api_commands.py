from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone

from . import tests as fixtures
from .models import SupplierInvoice
from .services import confirm_goods_receipt


class InvoiceReceiptApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.PurchasingServiceTests.setUpTestData.__func__(cls)
        cls.user = get_user_model().objects.create(email="invoice-api@example.test", is_superuser=True)

    create_receipt = fixtures.PurchasingServiceTests.create_receipt

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.invoice = SupplierInvoice.objects.create(supplier=self.supplier, invoice_number="API-INV", invoice_date=timezone.localdate(), taxable_amount="100.00", tax_amount="22.00", total_amount="122.00")

    def request(self, receipt):
        return self.client.post(f"/api/v1/purchasing/invoices/{self.invoice.pk}/set-receipts/", {"receipts": [str(receipt.pk)]}, format="json")

    def test_link_confirmed_receipt(self):
        receipt, _ = self.create_receipt()
        receipt = confirm_goods_receipt(receipt=receipt)
        result = self.request(receipt)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.invoice.receipt_links.get().receipt_id, receipt.pk)

    def test_draft_receipt_is_rejected(self):
        receipt, _ = self.create_receipt()
        self.assertEqual(self.request(receipt).status_code, 400)
        self.assertFalse(self.invoice.receipt_links.exists())

    def test_other_supplier_is_rejected(self):
        receipt, _ = self.create_receipt(supplier=self.other_supplier)
        receipt = confirm_goods_receipt(receipt=receipt)
        self.assertEqual(self.request(receipt).status_code, 400)
        self.assertFalse(self.invoice.receipt_links.exists())
