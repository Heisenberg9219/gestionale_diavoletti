from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductBarcode, ProductVariant, Size, SizeScale
from core.models import Location, TaxRate

from .services import post_stock_movement
from .models import StockMovement


class StockLevelFilterTests(TestCase):
    """Magazzino: filtri per livello di giacenza, ricerca per barcode e riepilogo."""

    @classmethod
    def setUpTestData(cls):
        tax_rate = TaxRate.objects.create(code="SL_VAT", name="IVA test", percentage="22.00")
        category = Category.objects.create(code="SL_CAT", name="Categoria test")
        scale = SizeScale.objects.create(code="SL_SCALE", name="Scala test", scale_type=SizeScale.Type.ALPHA)
        product = Product.objects.create(code="SL_PRODUCT", name="Felpa livelli", category=category, tax_rate=tax_rate)
        cls.shop = Location.objects.create(code="SL_SHOP", name="Negozio", type=Location.Type.SALES_FLOOR)
        cls.store = Location.objects.create(code="SL_STORE", name="Retro", type=Location.Type.OTHER)
        cls.variants = {}
        for index, (label, quantity) in enumerate((("A", 5), ("B", 2), ("C", 1))):
            size = Size.objects.create(size_scale=scale, code=f"SL_{label}", label=label, display_order=index)
            variant = ProductVariant.objects.create(product=product, sku=f"SL-{label}", size=size)
            post_stock_movement(
                variant=variant, location=cls.shop, movement_type=StockMovement.Type.INITIAL_STOCK,
                quantity_delta=quantity, unit_cost=Decimal("5.00"),
            )
            cls.variants[label] = variant
        # Una taglia venduta tutta: giacenza a zero nel negozio.
        post_stock_movement(
            variant=cls.variants["C"], location=cls.shop, movement_type=StockMovement.Type.ADJUSTMENT_OUT,
            quantity_delta=-1,
        )
        post_stock_movement(
            variant=cls.variants["A"], location=cls.store, movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=1, unit_cost=Decimal("5.00"),
        )
        ProductBarcode.objects.create(variant=cls.variants["B"], code="8000000000123", is_primary=True, barcode_type="OTHER", source="INTERNAL")
        ProductBarcode.objects.create(variant=cls.variants["B"], code="8000000000124", is_primary=False, barcode_type="OTHER", source="INTERNAL")
        User = get_user_model()
        cls.clerk = User.objects.create_user(email="sl-clerk@example.com", password="test-password")
        cls.clerk.groups.add(Group.objects.get_or_create(name="Commesso")[0])

    def get(self, query):
        client = APIClient()
        client.force_authenticate(self.clerk)
        response = client.get(f"/api/v1/inventory/stock/{query}")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def skus(self, data):
        return sorted((row["variant_sku"], row["location_name"]) for row in data.get("results", data))

    def test_level_filters(self):
        self.assertEqual(self.skus(self.get("?level=available")), [("SL-A", "Negozio")])
        self.assertEqual(self.skus(self.get("?level=low")), [("SL-A", "Retro"), ("SL-B", "Negozio")])
        self.assertEqual(self.skus(self.get("?level=zero")), [("SL-C", "Negozio")])

    def test_search_by_barcode_without_duplicates(self):
        self.assertEqual(self.skus(self.get("?search=800000000012")), [("SL-B", "Negozio")])

    def test_summary_counts_follow_location_and_ignore_level(self):
        data = self.get(f"summary/?location={self.shop.pk}&level=zero")
        self.assertEqual(
            {key: data[key] for key in ("total", "available", "low", "zero")},
            {"total": 3, "available": 1, "low": 1, "zero": 1},
        )
        self.assertEqual(self.get("summary/")["total"], 4)
