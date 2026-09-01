from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    BusinessDocument,
    DocumentNumberSequence,
    DocumentStatusChange,
    DocumentType,
)


def _record_status_change(*, document, previous_status, changed_by, reason=""):
    return DocumentStatusChange.objects.create(
        document=document,
        previous_status=previous_status,
        new_status=document.status,
        reason=reason.strip(),
        changed_by=changed_by,
    )


def _next_document_number(*, document_type, document_date):
    sequence, _ = DocumentNumberSequence.objects.get_or_create(
        document_type=document_type,
        year=document_date.year,
        defaults={"last_number": 0},
    )
    sequence = DocumentNumberSequence.objects.select_for_update().get(
        pk=sequence.pk
    )
    sequence.last_number += 1
    sequence.save(update_fields=("last_number", "updated_at"))
    prefix = document_type.number_prefix.strip() or document_type.code
    return f"{prefix}-{document_date.year}-{sequence.last_number:06d}"


@transaction.atomic
def finalize_document(*, document, finalized_by, number=None, finalized_at=None):
    document = BusinessDocument.objects.select_for_update().select_related(
        "document_type"
    ).get(pk=document.pk)
    if document.status != BusinessDocument.Status.DRAFT:
        raise ValidationError("Può essere finalizzato solo un documento in bozza.")
    if not document.document_type.is_active:
        raise ValidationError("La tipologia del documento non è attiva.")
    if document.direction != document.document_type.direction:
        raise ValidationError("La direzione non coincide con la tipologia.")

    if document.document_type.automatic_numbering:
        if number:
            raise ValidationError("Il numero è assegnato automaticamente.")
        document.number = _next_document_number(
            document_type=document.document_type,
            document_date=document.document_date,
        )
    elif number is not None:
        document.number = number.strip()

    if document.document_type.requires_number and not document.number:
        raise ValidationError("Il numero del documento è obbligatorio.")

    finalized_at = finalized_at or timezone.now()
    previous_status = document.status
    if document.direction == DocumentType.Direction.OUTGOING:
        document.status = BusinessDocument.Status.ISSUED
        document.issued_at = finalized_at
    else:
        document.status = BusinessDocument.Status.REGISTERED
        document.registered_at = finalized_at
    document.full_clean()
    document.save(update_fields=(
        "number", "status", "issued_at", "registered_at", "updated_at",
    ))
    _record_status_change(
        document=document,
        previous_status=previous_status,
        changed_by=finalized_by,
        reason="Documento finalizzato",
    )
    return document


@transaction.atomic
def cancel_document(*, document, cancelled_by, reason, cancelled_at=None):
    document = BusinessDocument.objects.select_for_update().get(pk=document.pk)
    if document.status == BusinessDocument.Status.CANCELLED:
        raise ValidationError("Il documento è già annullato.")
    if not reason.strip():
        raise ValidationError("L'annullamento richiede una motivazione.")
    previous_status = document.status
    document.status = BusinessDocument.Status.CANCELLED
    document.cancelled_at = cancelled_at or timezone.now()
    document.cancelled_by = cancelled_by
    document.cancellation_reason = reason.strip()
    document.save(update_fields=(
        "status", "cancelled_at", "cancelled_by",
        "cancellation_reason", "updated_at",
    ))
    _record_status_change(
        document=document,
        previous_status=previous_status,
        changed_by=cancelled_by,
        reason=reason,
    )
    return document
