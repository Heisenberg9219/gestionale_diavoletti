from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from core.models import TaxRate

from .models import Category, Product, ProductBarcode, ProductVariant, Size, SizeScale


class CatalogApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="catalog-owner@test.it", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        cls.clerk = get_user_model().objects.create_user(email="catalog-clerk@test.it", password="x")
        cls.clerk.groups.add(Group.objects.get(name="Commesso"))
        tax = TaxRate.objects.create(code="API_VAT", name="IVA API", percentage="22")
        category = Category.objects.create(code="API_CAT", name="Categoria API")
        scale = SizeScale.objects.create(code="API_SCALE", name="Scala API", scale_type=SizeScale.Type.ONE_SIZE)
        size = Size.objects.create(size_scale=scale, code="API_SIZE", label="Unica")
        product = Product.objects.create(code="API_PRODUCT", name="Prodotto ricercabile", category=category, tax_rate=tax)
        cls.variant = ProductVariant.objects.create(product=product, sku="API-SKU-001", size=size)
        ProductBarcode.objects.create(variant=cls.variant, code="8012345678901", barcode_type=ProductBarcode.Type.EAN13, source=ProductBarcode.Source.MANUFACTURER, is_primary=True)

    def test_clerk_can_search_variant_by_barcode(self):
        from accounts.models import UserPagePermission
        UserPagePermission.objects.create(user=self.clerk, page_key="Catalogo", can_view=True)
        self.client.force_authenticate(self.clerk)
        response = self.client.get("/api/v1/catalog/variants/?barcode=8012345678901")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["sku"], self.variant.sku)

    def test_clerk_cannot_modify_catalog(self):
        self.client.force_authenticate(self.clerk)
        response = self.client.patch(f"/api/v1/catalog/variants/{self.variant.pk}/", {"sku": "CHANGED"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_create_brand(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post("/api/v1/catalog/brands/", {"code": "API_BRAND", "name": "Marca API"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_unauthenticated_catalog_is_rejected(self):
        self.assertEqual(self.client.get("/api/v1/catalog/products/").status_code, 401)


class CostVisibilityTests(APITestCase):
    """Prezzi d'acquisto e ricarichi sono visibili solo al titolare."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import UserPagePermission
        cls.owner = get_user_model().objects.create_user(email="cost-owner@test.it", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        cls.clerk = get_user_model().objects.create_user(email="cost-clerk@test.it", password="x")
        cls.clerk.groups.add(Group.objects.get(name="Commesso"))
        UserPagePermission.objects.create(user=cls.clerk, page_key="Catalogo", can_view=True, can_update=True)
        tax = TaxRate.objects.create(code="COST_VAT", name="IVA", percentage="22")
        category = Category.objects.create(code="COST_CAT", name="Categoria")
        scale = SizeScale.objects.create(code="COST_SCALE", name="Scala", scale_type=SizeScale.Type.ONE_SIZE)
        size = Size.objects.create(size_scale=scale, code="COST_SIZE", label="Unica")
        product = Product.objects.create(code="COST_PRODUCT", name="Prodotto", category=category, tax_rate=tax)
        cls.variant = ProductVariant.objects.create(product=product, sku="COST-SKU", size=size, purchase_price="12.5000")

    def test_owner_sees_purchase_price(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(f"/api/v1/catalog/variants/{self.variant.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["purchase_price"], "12.5000")
        settings_response = self.client.get("/api/v1/core/settings/")
        self.assertIn("default_markup", settings_response.data["results"][0] if "results" in settings_response.data else settings_response.data[0])

    def test_clerk_cannot_read_or_overwrite_purchase_price(self):
        self.client.force_authenticate(self.clerk)
        response = self.client.get(f"/api/v1/catalog/variants/{self.variant.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("purchase_price", response.data)
        patch = self.client.patch(f"/api/v1/catalog/variants/{self.variant.pk}/", {"purchase_price": None}, format="json")
        self.assertEqual(patch.status_code, 200, patch.data)
        self.variant.refresh_from_db()
        self.assertEqual(str(self.variant.purchase_price), "12.5000")
        settings_response = self.client.get("/api/v1/core/settings/")
        rows = settings_response.data["results"] if "results" in settings_response.data else settings_response.data
        self.assertTrue(all("default_markup" not in row for row in rows))

    def test_clerk_cannot_read_inventory_costs(self):
        from accounts.models import UserPagePermission
        UserPagePermission.objects.create(user=self.clerk, page_key="Magazzino", can_view=True)
        self.client.force_authenticate(self.clerk)
        self.assertEqual(self.client.get("/api/v1/inventory/costs/").status_code, 403)
