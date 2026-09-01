from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventory.models import StockBalance

from .models import IntegrationConnection, SyncEvent, WebhookEvent


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
