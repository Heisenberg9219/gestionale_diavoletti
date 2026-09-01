from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class DocumentType(UUIDTimeStampedModel):
    class Direction(models.TextChoices):
        INCOMING = "INCOMING", "Ricevuto"
        OUTGOING = "OUTGOING", "Emesso"
        INTERNAL = "INTERNAL", "Interno"

    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    direction = models.CharField(max_length=16, choices=Direction.choices)
    requires_number = models.BooleanField(default=True)
    automatic_numbering = models.BooleanField(default=False)
    number_prefix = models.CharField(max_length=24, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("name",)

    def clean(self):
        if self.automatic_numbering and self.direction != self.Direction.OUTGOING:
            raise ValidationError(
                "La numerazione automatica è prevista solo per documenti emessi."
            )

    def __str__(self):
        return f"{self.code} - {self.name}"


class DocumentNumberSequence(UUIDTimeStampedModel):
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name="number_sequences",
    )
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("document_type", "year"),
                name="document_sequence_type_year",
            ),
        ]


class BusinessDocument(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Bozza"
        REGISTERED = "REGISTERED", "Registrato"
        ISSUED = "ISSUED", "Emesso"
        CANCELLED = "CANCELLED", "Annullato"

    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    direction = models.CharField(max_length=16, choices=DocumentType.Direction.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    number = models.CharField(max_length=80, blank=True)
    document_date = models.DateField()
    registered_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    title = models.CharField(max_length=200)
    taxable_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    counterparty_name = models.CharField(max_length=200, blank=True)
    counterparty_vat_number = models.CharField(max_length=32, blank=True)
    counterparty_tax_code = models.CharField(max_length=32, blank=True)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_business_documents",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_business_documents",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-document_date", "-created_at")
        indexes = [
            models.Index(
                fields=("status", "document_date"),
                name="document_status_date_idx",
            ),
            models.Index(
                fields=("source_type", "source_id"),
                name="document_source_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("document_type", "number"),
                condition=~Q(number=""),
                name="document_type_number_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(taxable_amount__gte=0)
                    & Q(tax_amount__gte=0)
                    & Q(total_amount__gte=0)
                ),
                name="document_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(total_amount=F("taxable_amount") + F("tax_amount")),
                name="document_total_matches",
            ),
            models.CheckConstraint(
                condition=(
                    Q(source_type="", source_id__isnull=True)
                    | (~Q(source_type="") & Q(source_id__isnull=False))
                ),
                name="document_source_pair_valid",
            ),
            models.CheckConstraint(
                condition=(~Q(status="ISSUED") | Q(issued_at__isnull=False)),
                name="document_issued_audit",
            ),
            models.CheckConstraint(
                condition=(~Q(status="REGISTERED") | Q(registered_at__isnull=False)),
                name="document_registered_audit",
            ),
        ]

    def __str__(self):
        return self.number or self.title


class DocumentAttachment(UUIDTimeStampedModel):
    document = models.ForeignKey(
        BusinessDocument,
        on_delete=models.PROTECT,
        related_name="attachments",
    )
    file = models.FileField(upload_to="documents/%Y/%m/")
    original_name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_document_attachments",
    )

    class Meta:
        ordering = ("created_at",)


class DocumentStatusChange(UUIDTimeStampedModel):
    document = models.ForeignKey(
        BusinessDocument,
        on_delete=models.PROTECT,
        related_name="status_changes",
    )
    previous_status = models.CharField(
        max_length=16,
        choices=BusinessDocument.Status.choices,
    )
    new_status = models.CharField(
        max_length=16,
        choices=BusinessDocument.Status.choices,
    )
    reason = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="changed_document_statuses",
    )

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(previous_status=F("new_status")),
                name="document_status_change_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Lo storico del documento è immutabile.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Lo storico del documento è immutabile.")
