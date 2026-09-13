from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    BusinessDocument,
    DocumentNumberSequence,
    DocumentAttachment,
    DocumentOcrAnalysis,
    DocumentStatusChange,
    DocumentType,
)


def _decimal_string(value):
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("amount", value.get("value"))
    elif hasattr(value, "amount"):
        value = value.amount
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _field_value(fields, name):
    field = fields.get(name)
    if field is None:
        return None
    value = getattr(field, "value", None)
    if value is not None:
        return value
    for attribute in (
        "value_string", "value_date", "value_time", "value_phone_number",
        "value_number", "value_integer", "value_currency", "value_address",
        "value_boolean", "value_array", "value_object", "value_country_region",
    ):
        value = getattr(field, attribute, None)
        if value is not None:
            return value
    return getattr(field, "content", None)


def _field_confidence(fields, name):
    field = fields.get(name)
    if field is None:
        return None
    confidence = getattr(field, "confidence", None)
    return float(confidence) if confidence is not None else None


def _azure_invoice_proposal(result):
    document = result.documents[0] if result.documents else None
    if document is None:
        raise ValidationError("Azure non ha riconosciuto una fattura nel PDF.")

    fields = document.fields
    items = []
    for item in _field_value(fields, "Items") or []:
        item_fields = getattr(item, "value_object", {}) or {}
        items.append({
            "description": _field_value(item_fields, "Description"),
            "quantity": _field_value(item_fields, "Quantity"),
            "unit_price": _decimal_string(_field_value(item_fields, "UnitPrice")),
            "amount": _decimal_string(_field_value(item_fields, "Amount")),
            "tax": _decimal_string(_field_value(item_fields, "Tax")),
        })

    return {
        "supplier_name": _field_value(fields, "VendorName"),
        "supplier_vat_number": _field_value(fields, "VendorTaxId"),
        "invoice_number": _field_value(fields, "InvoiceId"),
        "invoice_date": str(_field_value(fields, "InvoiceDate") or "") or None,
        "due_date": str(_field_value(fields, "DueDate") or "") or None,
        "currency": _currency_code(_field_value(fields, "InvoiceTotal")),
        "taxable_amount": _decimal_string(_field_value(fields, "SubTotal")),
        "tax_amount": _decimal_string(_field_value(fields, "TotalTax")),
        "total_amount": _decimal_string(_field_value(fields, "InvoiceTotal")),
        "items": items,
        "confidence": {
            "supplier_name": _field_confidence(fields, "VendorName"),
            "invoice_number": _field_confidence(fields, "InvoiceId"),
            "invoice_date": _field_confidence(fields, "InvoiceDate"),
            "total_amount": _field_confidence(fields, "InvoiceTotal"),
            "items": _field_confidence(fields, "Items"),
        },
    }


def _currency_code(value):
    if isinstance(value, dict):
        return value.get("currency_code") or value.get("currencyCode")
    return getattr(value, "currency_code", None)


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _analyze_with_azure(*, content):
    endpoint = getattr(settings, "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    api_key = getattr(settings, "AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    if not endpoint or not api_key:
        raise ImproperlyConfigured(
            "Configura AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT e "
            "AZURE_DOCUMENT_INTELLIGENCE_KEY nell'ambiente."
        )
    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
        from azure.core.credentials import AzureKeyCredential
    except ImportError as exc:
        raise ImproperlyConfigured(
            "Il pacchetto azure-ai-documentintelligence non è installato."
        ) from exc

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )
    poller = client.begin_analyze_document(
        "prebuilt-invoice",
        AnalyzeDocumentRequest(bytes_source=content),
    )
    return poller.result()


def analyze_invoice_attachment_with_azure(*, attachment, requested_by):
    attachment = DocumentAttachment.objects.get(pk=attachment.pk)
    if not attachment.file.name.lower().endswith(".pdf"):
        raise ValidationError("L'analisi OCR della fattura richiede un file PDF.")

    analysis = DocumentOcrAnalysis.objects.create(
        attachment=attachment,
        provider=DocumentOcrAnalysis.Provider.AZURE_DOCUMENT_INTELLIGENCE,
        requested_by=requested_by,
    )
    try:
        attachment.file.open("rb")
        try:
            result = _analyze_with_azure(content=attachment.file.read())
        finally:
            attachment.file.close()
        analysis.proposed_data = _azure_invoice_proposal(result)
        analysis.provider_response = _json_value(result.as_dict())
        analysis.status = DocumentOcrAnalysis.Status.SUCCEEDED
        analysis.analyzed_at = timezone.now()
        analysis.save(update_fields=(
            "proposed_data", "provider_response", "status", "analyzed_at", "updated_at",
        ))
    except Exception as exc:
        analysis.status = DocumentOcrAnalysis.Status.FAILED
        analysis.error_message = str(exc)
        analysis.analyzed_at = timezone.now()
        analysis.save(update_fields=(
            "status", "error_message", "analyzed_at", "updated_at",
        ))
    return analysis


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
