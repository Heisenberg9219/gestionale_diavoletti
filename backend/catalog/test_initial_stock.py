from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Location, TaxRate
from inventory.models import StockBalance, StockMovement, VariantInventoryCost

from .models import Category, Product, ProductVariant, Size, SizeScale


class InitialStockFromCatalogTests(TestCase):
    """Nuovo articolo dal catalogo con quantità: subito vendibile."""

    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(code="IS_VAT", name="IVA test", percentage="22.00")
        category = Category.objects.create(code="IS_CAT", name="Categoria test")
        scale = SizeScale.objects.create(code="IS_SCALE", name="Scala test", scale_type=SizeScale.Type.ONE_SIZE)
        size = Size.objects.create(size_scale=scale, code="IS_SIZE", label="Unica")
        product = Product.objects.create(code="IS_PRODUCT", name="Felpa test", category=category, tax_rate=tax_rate)
        cls.variant = ProductVariant.objects.create(
            product=product, sku="IS-SKU-1", size=size, purchase_price=Decimal("12.50"),
        )
        cls.location = Location.objects.create(code="IS_SHOP", name="Negozio", type=Location.Type.SALES_FLOOR)
        cls.other_location = Location.objects.create(code="IS_STORE", name="Magazzino", type=Location.Type.OTHER)
        User = get_user_model()
        cls.owner = User.objects.create_user(email="is-owner@example.com", password="test-password")
        cls.owner.groups.add(Group.objects.get_or_create(name="Titolare")[0])
        cls.clerk = User.objects.create_user(email="is-clerk@example.com", password="test-password")
        cls.clerk.groups.add(Group.objects.get_or_create(name="Commesso")[0])

    def url(self, variant=None):
        return f"/api/v1/catalog/variants/{(variant or self.variant).pk}/initial-stock/"

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_initial_stock_loads_quantity_with_purchase_cost(self):
        response = self.client_for(self.owner).post(
            self.url(), {"quantity": 5, "location": str(self.other_location.pk)}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity_on_hand"], 5)
        balance = StockBalance.objects.get(variant=self.variant, location=self.other_location)
        self.assertEqual(balance.quantity_on_hand, 5)
        movement = StockMovement.objects.get(variant=self.variant)
        self.assertEqual(movement.movement_type, StockMovement.Type.INITIAL_STOCK)
        self.assertEqual(movement.quantity_delta, 5)
        self.assertEqual(movement.reference_number, "IS-SKU-1")
        cost = VariantInventoryCost.objects.get(variant=self.variant)
        self.assertEqual(cost.total_quantity, 5)

    def test_default_location_is_first_active_one(self):
        response = self.client_for(self.owner).post(self.url(), {"quantity": 2}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(StockBalance.objects.filter(variant=self.variant, quantity_on_hand=2).exists())

    def test_second_initial_stock_is_refused(self):
        client = self.client_for(self.owner)
        self.assertEqual(client.post(self.url(), {"quantity": 1}, format="json").status_code, 201)
        response = client.post(self.url(), {"quantity": 3}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockMovement.objects.filter(variant=self.variant).count(), 1)

    def test_invalid_quantities_are_refused(self):
        client = self.client_for(self.owner)
        for value in (0, -2, "due", "", 10000):
            response = client.post(self.url(), {"quantity": value}, format="json")
            self.assertEqual(response.status_code, 400, value)
        self.assertFalse(StockMovement.objects.filter(variant=self.variant).exists())

    def test_invalid_location_is_refused(self):
        response = self.client_for(self.owner).post(self.url(), {"quantity": 1, "location": "non-un-id"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_clerk_cannot_load_initial_stock(self):
        response = self.client_for(self.clerk).post(self.url(), {"quantity": 1}, format="json")
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(StockMovement.objects.filter(variant=self.variant).exists())
