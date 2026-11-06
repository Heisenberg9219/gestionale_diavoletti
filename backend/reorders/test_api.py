from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from inventory.models import StockBalance

from django.test import TestCase

from . import tests as fixtures
from .models import ReorderItem


class ReorderApiTests(TestCase):
    """Lista riordini via API: aggiunta senza errori e righe leggibili."""

    @classmethod
    def setUpTestData(cls):
        fixtures.ReorderServiceTests.setUpTestData.__func__(cls)

    def setUp(self):
        fixtures.ReorderServiceTests.setUp(self)
        self.user.groups.add(Group.objects.get_or_create(name="Titolare")[0])
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def add(self, **extra):
        return self.client.post(
            "/api/v1/reorders/items/add/",
            {"variant": str(self.variant.pk), "location": str(self.location.pk), **extra},
            format="json",
        )

    def test_add_returns_created_item_with_readable_fields(self):
        StockBalance.objects.filter(pk=self.balance.pk).update(quantity_on_hand=1)
        response = self.add(requested_quantity=3)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["requested_quantity"], 3)
        self.assertEqual(response.data["variant_sku"], "REORDER_SKU")
        self.assertEqual(response.data["product_name"], "Prodotto test riordini")
        self.assertEqual(response.data["size_label"], "Taglia unica")
        self.assertEqual(response.data["location_name"], "Negozio test riordini")
        self.assertEqual(response.data["supplier_name"], "Fornitore riordini")
        self.assertEqual(response.data["stock_quantity"], 1)
        self.assertEqual(response.data["color_name"], "")

    def test_adding_same_item_twice_does_not_duplicate(self):
        self.assertEqual(self.add().status_code, 201)
        second = self.add()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(ReorderItem.objects.filter(status=ReorderItem.Status.PENDING).count(), 1)

    def test_list_is_readable(self):
        self.add()
        response = self.client.get("/api/v1/reorders/items/", {"status": "PENDING"})
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data.get("results", response.data)[0]
        self.assertEqual(row["product_name"], "Prodotto test riordini")
        self.assertEqual(row["stock_quantity"], 0)
