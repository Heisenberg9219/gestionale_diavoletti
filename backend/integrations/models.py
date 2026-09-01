from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import UUIDTimeStampedModel


class IntegrationConnection(UUIDTimeStampedModel):
    class Provider(models.TextChoices):
        SHOPIFY = "SHOPIFY", "Shopify"

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=24, choices=Provider.choices)
    shop_domain = models.CharField(max_length=255, blank=True)
    api_version = models.CharField(max_length=16, default="2026-07")
    credentials_env_prefix = models.CharField(max_length=64, default="SHOPIFY")
    is_active = models.BooleanField(default=True)
    online_locations = models.ManyToManyField(
        "core.Location", blank=True, related_name="integration_connections"
    )
    default_sale_location = models.ForeignKey(
        "core.Location", on_delete=models.PROTECT, null=True, blank=True,
        related_name="default_sale_integrations",
    )
    system_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="managed_integrations",
    )
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.code} - {self.name}"


class ExternalObjectMapping(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        PRODUCT = "PRODUCT", "Prodotto"
        VARIANT = "VARIANT", "Variante"
        CUSTOMER = "CUSTOMER", "Cliente"
        ORDER = "ORDER", "Ordine"

    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.CASCADE, related_name="mappings"
    )
    object_type = models.CharField(max_length=24, choices=Type.choices)
    internal_id = models.UUIDField()
    external_id = models.CharField(max_length=128)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("connection", "object_type", "internal_id"),
                name="int_map_internal_unique",
            ),
            models.UniqueConstraint(
                fields=("connection", "object_type", "external_id"),
                name="int_map_external_unique",
            ),
        ]


class SyncEvent(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        INVENTORY = "INVENTORY", "Giacenza"
        PRODUCT = "PRODUCT", "Prodotto"
        ORDER = "ORDER", "Ordine"

    class Status(models.TextChoices):
        PENDING = "PENDING", "In attesa"
        PROCESSING = "PROCESSING", "In elaborazione"
        RETRY = "RETRY", "Da riprovare"
        SUCCEEDED = "SUCCEEDED", "Completato"
        FAILED = "FAILED", "Fallito"

    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.CASCADE, related_name="sync_events"
    )
    event_type = models.CharField(max_length=24, choices=Type.choices)
    deduplication_key = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ("available_at", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("connection", "deduplication_key"),
                condition=Q(status__in=("PENDING", "PROCESSING", "RETRY")),
                name="int_sync_open_dedupe_unique",
            )
        ]
        indexes = [
            models.Index(fields=("status", "available_at"), name="int_sync_status_idx")
        ]


class WebhookEvent(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Ricevuto"
        PROCESSED = "PROCESSED", "Elaborato"
        FAILED = "FAILED", "Fallito"

    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.CASCADE, related_name="webhooks"
    )
    external_event_id = models.CharField(max_length=128)
    topic = models.CharField(max_length=96)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RECEIVED
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("connection", "external_event_id"),
                name="int_webhook_event_unique",
            )
        ]


class ImportedOrder(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Ricevuto"
        WAITING_PAYMENT = "WAITING_PAYMENT", "In attesa di pagamento"
        IMPORTED = "IMPORTED", "Importato"
        BLOCKED = "BLOCKED", "Bloccato"
        CANCELLED = "CANCELLED", "Annullato"

    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.PROTECT, related_name="orders"
    )
    external_id = models.CharField(max_length=128)
    order_number = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.RECEIVED
    )
    financial_status = models.CharField(max_length=32, blank=True)
    payload = models.JSONField(default=dict)
    sale = models.OneToOneField(
        "sales.Sale", on_delete=models.PROTECT, null=True, blank=True,
        related_name="imported_external_order",
    )
    error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("connection", "external_id"),
                name="int_imported_order_unique",
            )
        ]
