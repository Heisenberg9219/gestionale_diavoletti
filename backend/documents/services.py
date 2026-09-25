from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

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


MONEY = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise ValidationError("Importo non valido nella proposta OCR.") from exc


def _positive_quantity(value):
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("La quantità deve essere un numero intero.") from exc
    if quantity <= 0:
        raise ValidationError("La quantità deve essere maggiore di zero.")
    return quantity


def _new_code(prefix, value):
    """Genera codici tecnici univoci per entità nate dalla revisione OCR."""
    return f"{prefix}-{value.hex[:12].upper()}"


def _proposal_supplier(*, supplier_id, supplier_name, vat_number):
    from suppliers.models import Supplier

    if supplier_id:
        return Supplier.objects.get(pk=supplier_id, is_active=True)
    supplier_name = (supplier_name or "").strip()
    vat_number = (vat_number or "").strip()
    if not supplier_name:
        raise ValidationError("Indicare o selezionare il fornitore della fattura.")
    if vat_number:
        supplier = Supplier.objects.filter(vat_number=vat_number).first()
        if supplier:
            return supplier
    supplier = Supplier.objects.filter(business_name__iexact=supplier_name).first()
    if supplier:
        return supplier
    return Supplier.objects.create(
        code=_new_code("OCR-SUP", uuid4()),
        business_name=supplier_name,
        vat_number=vat_number,
    )


def _proposal_variant(*, item, user):
    from catalog.models import Product, ProductVariant
    from core.models import TaxRate

    variant_id = item.get("variant_id")
    if variant_id:
        return ProductVariant.objects.select_for_update().get(pk=variant_id, is_active=True)

    new_variant = item.get("new_variant") or {}
    sku = str(new_variant.get("sku") or "").strip()
    size_id = new_variant.get("size_id")
    if not sku or not size_id:
        raise ValidationError("Per un nuovo articolo indicare SKU e taglia.")
    product_id = new_variant.get("product_id")
    if product_id:
        product = Product.objects.get(pk=product_id, is_active=True)
    else:
        product_name = str(new_variant.get("product_name") or item.get("description") or "").strip()
        category_id = new_variant.get("category_id")
        tax_rate_id = new_variant.get("tax_rate_id")
        if not product_name or not category_id or not tax_rate_id:
            raise ValidationError("Per un nuovo prodotto indicare nome, categoria e IVA.")
        product = Product.objects.create(
            code=_new_code("OCR-PRD", uuid4()),
            name=product_name,
            category_id=category_id,
            tax_rate=TaxRate.objects.get(pk=tax_rate_id, is_active=True),
        )
    return ProductVariant.objects.create(
        product=product,
        sku=sku,
        color_id=new_variant.get("color_id") or None,
        size_id=size_id,
    )


@transaction.atomic
def apply_ocr_purchase_proposal(*, analysis, review, supplier_id=None, location_id=None, applied_by):
    """Turn an approved invoice proposal into document, purchase invoice and stock."""
    from core.models import Location
    from purchasing.models import (
        GoodsReceipt, GoodsReceiptLine, SupplierInvoice, SupplierInvoiceLine,
        SupplierInvoiceReceipt,
    )
    from purchasing.services import confirm_goods_receipt, confirm_supplier_invoice
    from suppliers.models import SupplierVariant

    analysis = DocumentOcrAnalysis.objects.select_for_update().select_related(
        "attachment__document",
    ).get(pk=analysis.pk)
    document = BusinessDocument.objects.select_for_update().select_related(
        "document_type",
    ).get(pk=analysis.attachment.document_id)
    if analysis.status != DocumentOcrAnalysis.Status.SUCCEEDED:
        raise ValidationError("La proposta OCR non è disponibile.")
    if analysis.proposed_data.get("review", {}).get("status") == "APPLIED":
        raise ValidationError("Questa proposta è già stata registrata.")
    if document.status != BusinessDocument.Status.DRAFT:
        raise ValidationError("Il documento non è più una bozza modificabile.")
    if document.direction != DocumentType.Direction.INCOMING:
        raise ValidationError("La registrazione OCR è prevista per fatture ricevute.")

    items = [item for item in review.get("items", []) if item.get("accepted", True)]
    if not items:
        raise ValidationError("Includere almeno una riga per registrare la fattura.")
    invoice_number = str(review.get("invoice_number") or "").strip()
    invoice_date = review.get("invoice_date")
    if not invoice_number or not invoice_date:
        raise ValidationError("Numero e data della fattura sono obbligatori.")
    location = Location.objects.get(pk=location_id, is_active=True) if location_id else Location.objects.filter(is_active=True).order_by("pk").first()
    if location is None:
        raise ValidationError("Selezionare la destinazione del carico in magazzino.")
    supplier = _proposal_supplier(
        supplier_id=supplier_id,
        supplier_name=review.get("supplier_name"),
        vat_number=analysis.proposed_data.get("supplier_vat_number"),
    )
    if SupplierInvoice.objects.filter(
        supplier=supplier, invoice_number=invoice_number,
    ).exists():
        raise ValidationError("Esiste già una fattura con questo numero per il fornitore selezionato.")

    prepared = []
    for item in items:
        quantity = _positive_quantity(item.get("quantity"))
        unit_cost = Decimal(str(item.get("unit_price")))
        if unit_cost < 0:
            raise ValidationError("Il costo unitario non può essere negativo.")
        variant = _proposal_variant(item=item, user=applied_by)
        prepared.append((item, variant, quantity, unit_cost))

    taxable_amount = sum((_money(quantity * cost) for _, _, quantity, cost in prepared), Decimal("0.00"))
    tax_rate = Decimal(str(review.get("tax_rate", review.get("tax_amount", "22"))))
    if tax_rate < 0 or tax_rate > 100:
        raise ValidationError("L'aliquota IVA deve essere compresa tra 0 e 100.")
    tax_amount = _money(taxable_amount * tax_rate / Decimal("100"))
    total_amount = taxable_amount + tax_amount

    receipt = GoodsReceipt.objects.create(
        number=_new_code("OCR-GR", analysis.pk), supplier=supplier,
        destination_location=location, received_at=timezone.now(),
        delivery_note_number=invoice_number, delivery_note_date=invoice_date,
        notes=f"Ricevimento creato da OCR {analysis.attachment.original_name}",
        created_by=applied_by,
    )
    receipt_lines = []
    for item, variant, quantity, unit_cost in prepared:
        receipt_line = GoodsReceiptLine.objects.create(
            receipt=receipt, variant=variant, quantity_received=quantity,
            unit_cost=unit_cost, notes=str(item.get("description") or ""),
        )
        receipt_lines.append(receipt_line)
        SupplierVariant.objects.get_or_create(
            supplier=supplier, variant=variant,
            defaults={"is_preferred": True},
        )
    confirm_goods_receipt(receipt=receipt, confirmed_by=applied_by)

    invoice = SupplierInvoice.objects.create(
        supplier=supplier, invoice_number=invoice_number, invoice_date=invoice_date,
        due_date=review.get("due_date") or None, taxable_amount=taxable_amount,
        tax_amount=tax_amount, total_amount=total_amount, created_by=applied_by,
        notes=f"Fattura creata da OCR {analysis.attachment.original_name}",
    )
    SupplierInvoiceReceipt.objects.create(invoice=invoice, receipt=receipt)
    remaining_tax = tax_amount
    for index, ((item, variant, quantity, unit_cost), receipt_line) in enumerate(zip(prepared, receipt_lines)):
        line_taxable = _money(quantity * unit_cost)
        line_tax = remaining_tax if index == len(prepared) - 1 else _money(line_taxable * tax_rate / Decimal("100"))
        remaining_tax -= line_tax
        SupplierInvoiceLine.objects.create(
            invoice=invoice, variant=variant, receipt_line=receipt_line,
            quantity_invoiced=quantity, final_unit_cost=unit_cost,
            tax_percentage=tax_rate, taxable_amount=line_taxable,
            tax_amount=line_tax, total_amount=line_taxable + line_tax,
            notes=str(item.get("description") or ""),
        )
    confirm_supplier_invoice(invoice=invoice, confirmed_by=applied_by)

    document.number = invoice_number
    document.document_date = invoice_date
    document.title = f"Fattura acquisto {invoice_number}"
    document.counterparty_name = supplier.business_name
    document.counterparty_vat_number = supplier.vat_number
    document.taxable_amount = taxable_amount
    document.tax_amount = tax_amount
    document.total_amount = total_amount
    document.source_type = "purchasing.SupplierInvoice"
    document.source_id = invoice.pk
    document.full_clean()
    document.save(update_fields=(
        "number", "document_date", "title", "counterparty_name",
        "counterparty_vat_number", "taxable_amount", "tax_amount",
        "total_amount", "source_type", "source_id", "updated_at",
    ))
    finalize_document(document=document, finalized_by=applied_by, number=invoice_number)

    saved_review = {
        **review, "tax_rate": str(tax_rate), "taxable_amount": str(taxable_amount),
        "tax_amount": str(tax_amount), "total_amount": str(total_amount),
        "status": "APPLIED", "applied_at": timezone.now().isoformat(),
        "supplier_id": str(supplier.pk), "location_id": str(location.pk),
        "invoice_id": str(invoice.pk), "receipt_id": str(receipt.pk),
    }
    analysis.proposed_data = {**analysis.proposed_data, "review": saved_review}
    analysis.save(update_fields=("proposed_data", "updated_at"))
    receipt.refresh_from_db()
    invoice.refresh_from_db()
    return {"document": document, "invoice": invoice, "receipt": receipt}


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
