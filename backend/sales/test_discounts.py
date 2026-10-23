from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from . import tests as fixtures
from .services import set_sale_line


class LineDiscountPercentageTests(TestCase):
    """Sconto % sul singolo articolo (prezzo base 24,90 €)."""

    @classmethod
    def setUpTestData(cls):
        fixtures.SalesServiceTests.setUpTestData.__func__(cls)
        cls.user.is_superuser = True
        cls.user.save()

    create_sale = fixtures.SalesServiceTests.create_sale

    def setUp(self):
        fixtures.SalesServiceTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.sale = self.create_sale()

    def set_line(self, **data):
        payload = {"variant": str(self.variant.pk), "quantity": 1, **data}
        return self.client.post(f"/api/v1/sales/sales/{self.sale.pk}/set-line/", payload, format="json")

    def test_percentage_discount_is_applied_to_the_line(self):
        response = self.set_line(quantity=2, discount_percentage="10")
        self.assertEqual(response.status_code, 200, response.data)
        line = self.sale.lines.get()
        self.assertEqual(line.base_unit_price, Decimal("24.90"))
        self.assertEqual(line.final_unit_price, Decimal("22.41"))
        self.assertEqual(line.net_amount, Decimal("44.82"))
        self.assertEqual(line.discount_amount, Decimal("4.98"))
        self.assertEqual(line.manual_discount_percentage, Decimal("10.00"))
        self.assertIn("10%", line.manual_override_reason)
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.final_total_amount, Decimal("44.82"))

    def test_discount_is_kept_when_quantity_changes(self):
        self.set_line(discount_percentage="10")
        response = self.set_line(quantity=3)
        self.assertEqual(response.status_code, 200, response.data)
        line = self.sale.lines.get()
        self.assertEqual(line.manual_discount_percentage, Decimal("10.00"))
        self.assertEqual(line.net_amount, Decimal("67.23"))

    def test_discount_is_kept_when_adding_by_scan(self):
        set_sale_line(sale=self.sale, variant=self.variant, quantity=1, discount_percentage="20")
        response = self.client.post(
            f"/api/v1/sales/sales/{self.sale.pk}/add-with-gift-check/",
            {"variant": str(self.variant.pk), "quantity": 2, "previous_quantity": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        line = self.sale.lines.get()
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.final_unit_price, Decimal("19.92"))

    def test_null_removes_the_discount(self):
        self.set_line(discount_percentage="10")
        response = self.set_line(discount_percentage=None)
        self.assertEqual(response.status_code, 200, response.data)
        line = self.sale.lines.get()
        self.assertIsNone(line.manual_discount_percentage)
        self.assertEqual(line.net_amount, Decimal("24.90"))

    def test_invalid_percentages_are_rejected(self):
        for value in ("0", "-5", "150", "abc"):
            with self.subTest(value=value):
                self.assertEqual(self.set_line(discount_percentage=value).status_code, 400)
        self.assertEqual(self.set_line(discount_percentage="10", manual_unit_price="5.00", reason="x").status_code, 400)

    def test_hundred_percent_makes_the_line_free(self):
        self.set_line(discount_percentage="100")
        self.assertEqual(self.sale.lines.get().net_amount, Decimal("0.00"))

    def test_total_override_after_line_discount(self):
        self.set_line(quantity=2, discount_percentage="10")
        response = self.client.post(
            f"/api/v1/sales/sales/{self.sale.pk}/set-total/",
            {"final_total_amount": "40.34", "reason": "Sconto 10% sul totale"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Decimal(response.data["final_total_amount"]), Decimal("40.34"))
        self.assertEqual(Decimal(response.data["calculated_total_amount"]), Decimal("44.82"))
