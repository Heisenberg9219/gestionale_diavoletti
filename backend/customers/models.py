from django.conf import settings
from django.db import models

from core.models import UUIDTimeStampedModel


class Customer(UUIDTimeStampedModel):
    customer_code = models.CharField(max_length=32, unique=True)
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=16, blank=True)
    city = models.CharField(max_length=120, blank=True)
    province = models.CharField(max_length=64, blank=True)
    country_code = models.CharField(max_length=2, default="IT")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_customers",
    )

    class Meta:
        ordering = ("last_name", "first_name", "customer_code")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.customer_code} - {self.full_name}"


class CustomerChild(UUIDTimeStampedModel):
    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Femminile"
        MALE = "MALE", "Maschile"
        NOT_SPECIFIED = "NOT_SPECIFIED", "Non specificato"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="children",
    )
    first_name = models.CharField(max_length=120)
    birth_date = models.DateField(null=True, blank=True)
    expected_birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=16,
        choices=Gender.choices,
        default=Gender.NOT_SPECIFIED,
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("first_name", "birth_date")

    def __str__(self):
        return f"{self.first_name} - {self.customer.full_name}"

class ConsentPurpose(UUIDTimeStampedModel):
    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    notice_text = models.TextField()
    notice_version = models.CharField(max_length=32)
    requires_double_opt_in = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CustomerConsentEvent(UUIDTimeStampedModel):
    class Action(models.TextChoices):
        GRANTED = "GRANTED", "Concesso"
        WITHDRAWN = "WITHDRAWN", "Revocato"
        CONFIRMATION_REQUESTED = (
            "CONFIRMATION_REQUESTED",
            "Conferma richiesta",
        )
        CONFIRMED = "CONFIRMED", "Confermato"

    class Channel(models.TextChoices):
        IN_STORE_SMARTPHONE = (
            "IN_STORE_SMARTPHONE",
            "Smartphone in negozio",
        )
        WEB = "WEB", "Web"
        EMAIL = "EMAIL", "Email"
        IMPORT = "IMPORT", "Importazione"

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="consent_events",
    )
    purpose = models.ForeignKey(
        ConsentPurpose,
        on_delete=models.PROTECT,
        related_name="consent_events",
    )
    action = models.CharField(
        max_length=24,
        choices=Action.choices,
    )
    notice_version = models.CharField(max_length=32)
    notice_text = models.TextField()
    occurred_at = models.DateTimeField()
    channel = models.CharField(
        max_length=24,
        choices=Channel.choices,
    )
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collected_customer_consents",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    related_event = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="follow_up_events",
    )

    class Meta:
        ordering = ("-occurred_at", "-created_at")
        indexes = [
            models.Index(
                fields=("customer", "purpose", "occurred_at"),
                name="customer_consent_history_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.customer.customer_code} - "
            f"{self.purpose.code}: {self.action}"
        )