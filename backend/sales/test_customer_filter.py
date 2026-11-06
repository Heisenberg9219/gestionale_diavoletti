from django.test import TestCase
from rest_framework.test import APIClient

from customers.models import Customer

from . import tests as fixtures
from .models import Sale


class SaleCustomerFilterTests(TestCase):
    """Scheda cliente: lo storico vendite si filtra per cliente."""

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

    def test_sales_filtered_by_customer(self):
        anna = Customer.objects.create(customer_code="CF-ANNA", first_name="Anna", last_name="Rossi")
        luca = Customer.objects.create(customer_code="CF-LUCA", first_name="Luca", last_name="Verdi")
        first = self.create_sale()
        Sale.objects.filter(pk=first.pk).update(customer=anna)
        second = Sale.objects.create(cash_session=first.cash_session, location=self.location, opened_by=self.user, customer=luca)
        Sale.objects.create(cash_session=first.cash_session, location=self.location, opened_by=self.user)
        response = self.client.get("/api/v1/sales/sales/", {"customer": str(anna.pk)})
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data.get("results", response.data)
        self.assertEqual([row["id"] for row in rows], [str(first.pk)])
        response = self.client.get("/api/v1/sales/sales/", {"customer": str(luca.pk)})
        rows = response.data.get("results", response.data)
        self.assertEqual([row["id"] for row in rows], [str(second.pk)])
