from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import patch

from catalog.models import Category, Product, ProductVariant, Size, SizeScale
from core.models import Location, TaxRate
from inventory.models import StockMovement
from inventory.services import post_stock_movement

from .models import ExternalObjectMapping, IntegrationConnection, SyncEvent, WebhookEvent
from .services import available_online_quantity, process_sync_event, register_webhook


class IntegrationServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(email="integration@test.it", password="x")
        tax = TaxRate.objects.create(code="INT_VAT", name="IVA integrazioni", percentage="22")
        category = Category.objects.create(code="INT_CAT", name="Categoria integrazioni")
        scale = SizeScale.objects.create(code="INT_SCALE", name="Scala integrazioni", scale_type=SizeScale.Type.ONE_SIZE)
        size = Size.objects.create(size_scale=scale, code="INT_SIZE", label="Unica")
        product = Product.objects.create(code="INT_PRODUCT", name="Prodotto integrazioni", category=category, tax_rate=tax)
        cls.variant = ProductVariant.objects.create(product=product, sku="INT-SKU", size=size)
        cls.first = Location.objects.create(code="INT_LOC_1", name="Negozio", type=Location.Type.SALES_FLOOR)
        cls.second = Location.objects.create(code="INT_LOC_2", name="Magazzino", type=Location.Type.STOCKROOM)
        cls.connection = IntegrationConnection.objects.create(code="SHOPIFY_TEST", name="Shopify test", provider=IntegrationConnection.Provider.SHOPIFY, system_user=user, default_sale_location=cls.first)
        cls.connection.online_locations.add(cls.first, cls.second)

    def test_online_quantity_sums_enabled_locations(self):
        for location, quantity in ((self.first, 2), (self.second, 3)):
            post_stock_movement(variant=self.variant, location=location, movement_type=StockMovement.Type.INITIAL_STOCK, quantity_delta=quantity, unit_cost="10")
        self.assertEqual(available_online_quantity(connection=self.connection, variant=self.variant), 5)

    def test_webhook_is_idempotent(self):
        first, created = register_webhook(connection=self.connection, external_event_id="evt-1", topic="orders/paid", payload={"id": 1})
        second, created_again = register_webhook(connection=self.connection, external_event_id="evt-1", topic="orders/paid", payload={"id": 1})
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_stock_movement_enqueues_real_quantity(self):
        post_stock_movement(variant=self.variant, location=self.first, movement_type=StockMovement.Type.INITIAL_STOCK, quantity_delta=4, unit_cost="10")
        event = SyncEvent.objects.get(event_type=SyncEvent.Type.INVENTORY)
        self.assertEqual(event.payload["quantity"], 4)

    @patch("integrations.services._shopify_graphql")
    def test_inventory_event_sends_quantity_for_each_online_location(self, graphql):
        post_stock_movement(
            variant=self.variant,
            location=self.first,
            movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=2,
            unit_cost="10",
        )
        post_stock_movement(
            variant=self.variant,
            location=self.second,
            movement_type=StockMovement.Type.INITIAL_STOCK,
            quantity_delta=3,
            unit_cost="10",
        )
        ExternalObjectMapping.objects.create(
            connection=self.connection,
            object_type=ExternalObjectMapping.Type.VARIANT,
            internal_id=self.variant.pk,
            external_id="gid://shopify/ProductVariant/10",
            metadata={"inventory_item_id": "gid://shopify/InventoryItem/20"},
        )
        for location, external_id in (
            (self.first, "gid://shopify/Location/1"),
            (self.second, "gid://shopify/Location/2"),
        ):
            ExternalObjectMapping.objects.create(
                connection=self.connection,
                object_type=ExternalObjectMapping.Type.LOCATION,
                internal_id=location.pk,
                external_id=external_id,
            )
        graphql.return_value = {"inventorySetQuantities": {"userErrors": []}}

        event = SyncEvent.objects.get(event_type=SyncEvent.Type.INVENTORY)
        processed = process_sync_event(event=event)

        self.assertEqual(processed.status, SyncEvent.Status.SUCCEEDED)
        quantities = graphql.call_args.kwargs["variables"]["input"]["quantities"]
        self.assertEqual({row["quantity"] for row in quantities}, {2, 3})
