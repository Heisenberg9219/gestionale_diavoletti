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
