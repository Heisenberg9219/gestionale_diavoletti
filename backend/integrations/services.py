import json
import os
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import ProductVariant
from inventory.models import StockBalance

from .models import (
    ExternalObjectMapping,
    ImportedOrder,
    IntegrationConnection,
    SyncEvent,
    WebhookEvent,
)


SHOPIFY_GRAPHQL_MUTATION = """
mutation inventorySet($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    userErrors { field message }
  }
}
"""


def _shopify_access_token(connection):
    variable = f"{connection.credentials_env_prefix}_ACCESS_TOKEN"
    token = os.environ.get(variable, "").strip()
    if not token:
        raise ImproperlyConfigured(
            f"Configura la variabile d'ambiente {variable} per Shopify."
        )
    return token


def _shopify_graphql(*, connection, query, variables):
    domain = connection.shop_domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
    if not domain:
        raise ImproperlyConfigured("Configura il dominio del negozio Shopify.")
    if "/" in domain or not domain.endswith(".myshopify.com"):
        raise ValidationError("Il dominio Shopify deve terminare con .myshopify.com.")

    request = Request(
        f"https://{domain}/admin/api/{connection.api_version}/graphql.json",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": _shopify_access_token(connection),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValidationError(f"Shopify ha risposto HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise ValidationError(f"Shopify non raggiungibile: {exc.reason}") from exc

    if payload.get("errors"):
        raise ValidationError(f"Errore Shopify: {payload['errors']}")
    return payload.get("data", {})


def _mapping_for(*, connection, object_type, internal_id):
    return ExternalObjectMapping.objects.filter(
        connection=connection,
        object_type=object_type,
        internal_id=internal_id,
    ).first()


def _sync_shopify_inventory(*, event):
    variant = ProductVariant.objects.get(pk=event.payload["variant_id"])
    variant_mapping = _mapping_for(
        connection=event.connection,
        object_type=ExternalObjectMapping.Type.VARIANT,
        internal_id=variant.pk,
    )
    if variant_mapping is None:
        raise ValidationError(f"Manca il mapping Shopify per la variante {variant.sku}.")
    inventory_item_id = variant_mapping.metadata.get("inventory_item_id")
    if not inventory_item_id:
        raise ValidationError(
            f"Il mapping della variante {variant.sku} non contiene inventory_item_id."
        )

    locations = list(event.connection.online_locations.all())
    if not locations:
        raise ValidationError("La connessione Shopify non ha sedi online configurate.")
    quantities = []
    for location in locations:
        location_mapping = _mapping_for(
            connection=event.connection,
            object_type=ExternalObjectMapping.Type.LOCATION,
            internal_id=location.pk,
        )
        if location_mapping is None:
            raise ValidationError(f"Manca il mapping Shopify per la sede {location.name}.")
        quantities.append({
            "inventoryItemId": inventory_item_id,
            "locationId": location_mapping.external_id,
            "quantity": StockBalance.objects.filter(
                variant=variant,
                location=location,
            ).aggregate(total=Sum("quantity_on_hand"))["total"] or 0,
        })

    data = _shopify_graphql(
        connection=event.connection,
        query=SHOPIFY_GRAPHQL_MUTATION,
        variables={
            "input": {
                "name": "available",
                "reason": "correction",
                "ignoreCompareQuantity": True,
                "quantities": quantities,
            },
        },
    )
    errors = data.get("inventorySetQuantities", {}).get("userErrors", [])
    if errors:
        raise ValidationError(f"Shopify ha rifiutato la giacenza: {errors}")


@transaction.atomic
def process_sync_event(*, event):
    event = SyncEvent.objects.select_for_update().select_related("connection").get(pk=event.pk)
    if event.status not in {SyncEvent.Status.PENDING, SyncEvent.Status.RETRY}:
        raise ValidationError("L'evento non è elaborabile.")
    if event.available_at > timezone.now():
        raise ValidationError("L'evento non è ancora disponibile.")

    event.status = SyncEvent.Status.PROCESSING
    event.attempts += 1
    event.save(update_fields=("status", "attempts", "updated_at"))
    try:
        if event.connection.provider != IntegrationConnection.Provider.SHOPIFY:
            raise ValidationError("Provider di sincronizzazione non supportato.")
        if event.event_type != SyncEvent.Type.INVENTORY:
            raise ValidationError("Tipo evento di sincronizzazione non supportato.")
        _sync_shopify_inventory(event=event)
    except Exception as exc:
        exhausted = event.attempts >= 5
        event.status = SyncEvent.Status.FAILED if exhausted else SyncEvent.Status.RETRY
        event.available_at = timezone.now() + timedelta(minutes=2 ** min(event.attempts, 6))
        event.last_error = str(exc)
        event.save(update_fields=("status", "available_at", "last_error", "updated_at"))
        connection = event.connection
        connection.last_error_at = timezone.now()
        connection.last_error = str(exc)
        connection.save(update_fields=("last_error_at", "last_error", "updated_at"))
        return event

    event.status = SyncEvent.Status.SUCCEEDED
    event.processed_at = timezone.now()
    event.last_error = ""
    event.save(update_fields=("status", "processed_at", "last_error", "updated_at"))
    connection = event.connection
    connection.last_success_at = timezone.now()
    connection.last_error = ""
    connection.save(update_fields=("last_success_at", "last_error", "updated_at"))
    return event


def process_available_sync_events(*, limit=50):
    events = SyncEvent.objects.filter(
        status__in=(SyncEvent.Status.PENDING, SyncEvent.Status.RETRY),
        available_at__lte=timezone.now(),
    ).order_by("available_at", "created_at")[:limit]
    return [process_sync_event(event=event) for event in events]


def _shopify_variant_mapping(*, connection, external_variant_id):
    candidates = {
        str(external_variant_id),
        f"gid://shopify/ProductVariant/{external_variant_id}",
    }
    return ExternalObjectMapping.objects.filter(
        connection=connection,
        object_type=ExternalObjectMapping.Type.VARIANT,
        external_id__in=candidates,
    ).first()


@transaction.atomic
def import_paid_shopify_order(*, connection, payload):
    external_id = str(payload.get("id", "")).strip()
    if not external_id:
        raise ValidationError("L'ordine Shopify non contiene l'identificativo.")
    order, created = ImportedOrder.objects.select_for_update().get_or_create(
        connection=connection,
        external_id=external_id,
        defaults={
            "order_number": str(payload.get("name", "")),
            "financial_status": str(payload.get("financial_status", "")),
            "payload": payload,
        },
    )
    if not created and order.status == ImportedOrder.Status.IMPORTED:
        return order

    order.order_number = str(payload.get("name", ""))
    order.financial_status = str(payload.get("financial_status", ""))
    order.payload = payload
    if order.financial_status.lower() not in {"paid", "partially_paid"}:
        order.status = ImportedOrder.Status.WAITING_PAYMENT
        order.save(update_fields=("order_number", "financial_status", "payload", "status", "updated_at"))
        return order
    if connection.default_sale_location_id is None or connection.system_user_id is None:
        order.status = ImportedOrder.Status.BLOCKED
        order.error = "La connessione Shopify richiede sede vendite e utente tecnico."
        order.save(update_fields=("order_number", "financial_status", "payload", "status", "error", "updated_at"))
        return order

    from sales.models import Sale, SalePayment
    from sales.services import add_sale_payment, confirm_sale, set_sale_line

    savepoint = transaction.savepoint()
    sale = Sale.objects.create(
        channel=Sale.Channel.SHOPIFY,
        location=connection.default_sale_location,
        opened_by=connection.system_user,
        notes=f"Ordine Shopify {order.order_number or external_id}",
    )
    try:
        aggregated = {}
        for item in payload.get("line_items", []):
            mapping = _shopify_variant_mapping(
                connection=connection,
                external_variant_id=item.get("variant_id"),
            )
            if mapping is None:
                raise ValidationError(f"Variante Shopify non mappata: {item.get('variant_id')}.")
            quantity = int(item.get("quantity", 0))
            if quantity <= 0:
                raise ValidationError("Una riga Shopify ha una quantità non valida.")
            price = Decimal(str(item.get("price", "0")))
            discount = Decimal(str(item.get("total_discount", "0")))
            unit_price = (price * quantity - discount) / quantity
            previous = aggregated.get(mapping.internal_id)
            if previous and previous["unit_price"] != unit_price:
                raise ValidationError("La stessa variante Shopify ha prezzi diversi nello stesso ordine.")
            aggregated[mapping.internal_id] = {"quantity": quantity + (previous or {}).get("quantity", 0), "unit_price": unit_price}

        if not aggregated:
            raise ValidationError("L'ordine Shopify non contiene articoli vendibili.")
        for variant_id, item in aggregated.items():
            set_sale_line(
                sale=sale,
                variant=ProductVariant.objects.get(pk=variant_id),
                quantity=item["quantity"],
                manual_unit_price=item["unit_price"],
                manual_override_reason="Prezzo importato da Shopify.",
                manual_override_by=connection.system_user,
            )
        sale.refresh_from_db()
        add_sale_payment(
            sale=sale,
            method=SalePayment.Method.CARD,
            amount=sale.final_total_amount,
            transaction_reference=external_id,
            source_type="shopify.Order",
            created_by=connection.system_user,
        )
        sale = confirm_sale(sale=sale, confirmed_by=connection.system_user)
    except Exception as exc:
        transaction.savepoint_rollback(savepoint)
        order.status = ImportedOrder.Status.BLOCKED
        order.error = str(exc)
        order.save(update_fields=("order_number", "financial_status", "payload", "status", "error", "updated_at"))
        return order

    transaction.savepoint_commit(savepoint)

    order.status = ImportedOrder.Status.IMPORTED
    order.sale = sale
    order.error = ""
    order.save(update_fields=("order_number", "financial_status", "payload", "status", "sale", "error", "updated_at"))
    return order


def available_online_quantity(*, connection, variant):
    return StockBalance.objects.filter(
        variant=variant,
        location__in=connection.online_locations.all(),
    ).aggregate(total=Sum("quantity_on_hand"))["total"] or 0


@transaction.atomic
def enqueue_inventory_sync(*, variant, location=None):
    connections = IntegrationConnection.objects.filter(
        provider=IntegrationConnection.Provider.SHOPIFY,
        is_active=True,
        online_locations__isnull=False,
    ).distinct()
    if location is not None:
        connections = connections.filter(online_locations=location)
    events = []
    for connection in connections:
        quantity = available_online_quantity(connection=connection, variant=variant)
        key = f"inventory:{variant.pk}"
        event = SyncEvent.objects.select_for_update().filter(
            connection=connection,
            deduplication_key=key,
            status__in=(
                SyncEvent.Status.PENDING,
                SyncEvent.Status.PROCESSING,
                SyncEvent.Status.RETRY,
            ),
        ).order_by("pk").first()
        if event is None:
            event = SyncEvent.objects.create(
                connection=connection,
                event_type=SyncEvent.Type.INVENTORY,
                deduplication_key=key,
                payload={"variant_id": str(variant.pk), "quantity": quantity},
                available_at=timezone.now(),
            )
        else:
            event.payload = {"variant_id": str(variant.pk), "quantity": quantity}
            event.status = SyncEvent.Status.PENDING
            event.available_at = timezone.now()
            event.last_error = ""
            event.save(update_fields=(
                "payload", "status", "available_at", "last_error", "updated_at",
            ))
        events.append(event)
    return events


@transaction.atomic
def register_webhook(*, connection, external_event_id, topic, payload):
    if not external_event_id:
        raise ValidationError("Il webhook richiede un identificativo esterno.")
    return WebhookEvent.objects.get_or_create(
        connection=connection,
        external_event_id=external_event_id,
        defaults={"topic": topic, "payload": payload},
    )
