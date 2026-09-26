from decimal import Decimal
from difflib import SequenceMatcher
from datetime import date

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


def _positive_integer(value, field_name):
    try:
        numeric = Decimal(str(value))
        if not numeric.is_finite() or numeric != numeric.to_integral_value():
            raise ValueError()
        value = int(numeric)
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise ValidationError({field_name: "Inserisci una quantità intera positiva."}) from exc
    if value < 1:
        raise ValidationError({field_name: "Inserisci una quantità intera positiva."})
    return value


def _money(value, field_name, *, positive=False):
    try:
        value = Decimal(str(value).replace(",", "."))
    except Exception as exc:
        raise ValidationError({field_name: "Inserisci un importo valido."}) from exc
    if not value.is_finite() or value < 0 or (positive and value <= 0):
        raise ValidationError({field_name: "L'importo non è valido."})
    return value


@transaction.atomic
def import_ocr_review_to_inventory(*, attachment, imported_by, analysis_id):
    """Create and confirm one goods receipt from a reviewed OCR proposal."""
    from catalog.models import Product, ProductBarcode, ProductVariant
    from purchasing.models import GoodsReceipt, GoodsReceiptLine
    from purchasing.services import confirm_goods_receipt

    attachment = DocumentAttachment.objects.select_for_update().get(pk=attachment.pk)
    document = BusinessDocument.objects.select_for_update().get(pk=attachment.document_id)
    analysis = DocumentOcrAnalysis.objects.select_for_update().get(pk=analysis_id, attachment=attachment, status="SUCCEEDED")
    review = analysis.proposed_data.get("review", {})
    errors = validate_ocr_review(review)
    if errors:
        raise ValidationError(errors)
    from suppliers.models import Supplier
    from core.models import Location
    supplier = Supplier.objects.get(pk=review["supplier"])
    location = Location.objects.get(pk=review["location"])
    lines = [dict(item, unit_cost=item.get("unit_price")) for item in review["items"] if item.get("accepted", True)]
    if document.direction != "INCOMING" or document.status == "CANCELLED":
        raise ValidationError("Il carico richiede un documento di acquisto ricevuto e non annullato.")
    if document.source_type == "GOODS_RECEIPT":
        raise ValidationError("Questo documento è già stato caricato in magazzino.")
    receipt_number = f"OCR-{attachment.pk.hex[:16].upper()}"
    if GoodsReceipt.objects.filter(number=receipt_number).exists():
        raise ValidationError("Questa proposta OCR è già stata caricata in magazzino.")
    if not lines:
        raise ValidationError("Seleziona almeno un articolo da caricare.")

    receipt = GoodsReceipt.objects.create(
        number=receipt_number,
        supplier=supplier,
        destination_location=location,
        delivery_note_number=review["invoice_number"].strip(),
        delivery_note_date=date.fromisoformat(review["invoice_date"]),
        notes=f"Carico creato dalla proposta OCR del documento {attachment.document_id}.",
        created_by=imported_by,
    )

    seen_variants = set()
    for index, line in enumerate(lines, start=1):
        variant_id = line.get("variant_id")
        if variant_id:
            try:
                variant = ProductVariant.objects.select_related("product").get(pk=variant_id)
            except ProductVariant.DoesNotExist as exc:
                raise ValidationError({"lines": f"Riga {index}: articolo selezionato non trovato."}) from exc
        else:
            product_data = line.get("new_product") or {}
            required_fields = ("name", "category", "tax_rate", "size", "sku")
            missing = [field for field in required_fields if not product_data.get(field)]
            if missing:
                raise ValidationError({"lines": f"Riga {index}: completa i dati del nuovo articolo ({', '.join(missing)})."})
            sku = str(product_data["sku"]).strip()
            barcode = str(product_data.get("barcode", "")).strip()
            if ProductVariant.objects.filter(sku__iexact=sku).exists() or (barcode and ProductBarcode.objects.filter(code=barcode).exists()):
                raise ValidationError({"lines": f"Riga {index}: SKU o barcode già presenti. Associa l'articolo esistente."})
            name = str(product_data["name"]).strip()
            if Product.objects.filter(name__iexact=name).exists():
                raise ValidationError({"lines": f"Riga {index}: esiste già un prodotto con questo nome. Associalo invece di duplicarlo."})
            product = Product(
                code=f"OCR-{attachment.pk.hex[:10].upper()}-{index}",
                name=name,
                category_id=product_data["category"],
                tax_rate_id=product_data["tax_rate"],
            )
            product.full_clean()
            product.save()
            variant = ProductVariant(
                product=product,
                sku=sku,
                size_id=product_data["size"],
                color_id=product_data.get("color") or None,
            )
            variant.full_clean()
            variant.save()
            if barcode:
                product_barcode = ProductBarcode(
                    variant=variant, code=barcode, barcode_type="OTHER",
                    source="MANUFACTURER", is_primary=True,
                )
                product_barcode.full_clean()
                product_barcode.save()

        if variant.pk in seen_variants:
            raise ValidationError({"lines": f"Riga {index}: la stessa variante è presente più volte."})
        seen_variants.add(variant.pk)
        receipt_line = GoodsReceiptLine(
            receipt=receipt,
            variant=variant,
            quantity_received=_positive_integer(line.get("quantity"), "quantity"),
            unit_cost=_money(line.get("unit_cost"), "unit_cost"),
            final_sale_price=_money(line.get("sale_price"), "sale_price", positive=True) if line.get("sale_price") not in (None, "") else None,
            notes=str(line.get("description", "")).strip(),
        )
        receipt_line.full_clean()
        receipt_line.save()

    receipt = confirm_goods_receipt(receipt=receipt, confirmed_by=imported_by)
    document.number = review["invoice_number"].strip()
    document.document_date = date.fromisoformat(review["invoice_date"])
    document.counterparty_name = review.get("supplier_name") or supplier.business_name
    document.taxable_amount = _money(review["taxable_amount"], "imponibile")
    document.total_amount = _money(review["total_amount"], "totale")
    document.tax_amount = document.total_amount - document.taxable_amount
    document.source_type = "GOODS_RECEIPT"
    document.source_id = receipt.pk
    document.full_clean()
    document.save()
    if document.status == "DRAFT":
        finalize_document(document=document, finalized_by=imported_by)
    review = dict(review, status="IMPORTED", receipt_id=str(receipt.pk), imported_at=timezone.now().isoformat())
    analysis.proposed_data = dict(analysis.proposed_data, review=review)
    analysis.save(update_fields=("proposed_data", "updated_at"))
    return receipt


def validate_ocr_review(review):
    """Return blocking errors, including collisions inside the proposal itself."""
    from catalog.models import Category, Color, Product, ProductBarcode, ProductVariant, Size
    from core.models import Location, TaxRate
    from suppliers.models import Supplier
    errors = []
    def reference(model, value, label):
        try:
            valid = model.objects.filter(pk=value, is_active=True).exists() if value else False
        except (ValidationError, ValueError, TypeError):
            valid = False
        if not valid:
            errors.append(f"{label}: seleziona un valore attivo valido.")
    reference(Supplier, review.get("supplier"), "Fornitore")
    reference(Location, review.get("location"), "Sede")
    if not str(review.get("invoice_number") or "").strip():
        errors.append("Inserisci il numero fattura.")
    try:
        date.fromisoformat(review.get("invoice_date", ""))
        taxable = _money(review.get("taxable_amount"), "Imponibile")
        total = _money(review.get("total_amount"), "Totale")
        rate = _money(review.get("tax_rate"), "Aliquota IVA")
        if total < taxable or rate > 100:
            raise ValueError()
    except (ValidationError, ValueError, TypeError):
        errors.append("Controlla data, imponibile, aliquota IVA e totale fattura.")
    items = review.get("items", [])
    if not isinstance(items, list):
        return errors + ["Le righe della proposta non sono valide."]
    included = [item for item in items if isinstance(item, dict) and item.get("accepted", True)]
    if not included:
        errors.append("Includi almeno una riga.")
    names = list(Product.objects.values_list("name", flat=True))
    skus, barcodes, variants = set(), set(), set()
    for index, item in enumerate(included, 1):
        prefix = f"Riga {index}"
        try:
            _positive_integer(item.get("quantity"), "Quantità")
            _money(item.get("unit_price"), "Costo")
            _money(item.get("sale_price"), "Prezzo vendita", positive=True)
        except (ValidationError, ArithmeticError):
            errors.append(f"{prefix}: quantità intera positiva, costo e prezzo vendita sono obbligatori.")
        if item.get("variant_id"):
            reference(ProductVariant, item["variant_id"], prefix)
            try:
                if ProductVariant.objects.filter(pk=item["variant_id"], product__is_active=False).exists():
                    errors.append(f"{prefix}: il prodotto selezionato non è attivo.")
            except (ValidationError, ValueError, TypeError):
                pass
            if item["variant_id"] in variants:
                errors.append(f"{prefix}: variante ripetuta nella proposta.")
            variants.add(item["variant_id"])
            continue
        data = item.get("new_product") or {}
        if not isinstance(data, dict):
            errors.append(f"{prefix}: dati articolo non validi.")
            continue
        name, sku, barcode = (str(data.get(key) or "").strip() for key in ("name", "sku", "barcode"))
        if not name or not sku:
            errors.append(f"{prefix}: nome e SKU sono obbligatori.")
        if len(name) > 160 or len(sku) > 64 or len(barcode) > 128:
            errors.append(f"{prefix}: nome (160), SKU (64) o barcode (128) superano la lunghezza massima.")
        for model, key in ((Category, "category"), (TaxRate, "tax_rate"), (Size, "size")):
            reference(model, data.get(key), f"{prefix} {key}")
        if data.get("color"):
            reference(Color, data["color"], f"{prefix} colore")
        if sku.casefold() in skus or ProductVariant.objects.filter(sku__iexact=sku).exists():
            errors.append(f"{prefix}: SKU già presente. Associa la variante esistente o correggi lo SKU.")
        if barcode and (barcode.casefold() in barcodes or ProductBarcode.objects.filter(code__iexact=barcode).exists()):
            errors.append(f"{prefix}: barcode già presente. Associa la variante esistente.")
        normalized = " ".join(name.casefold().split())
        matches = [other for other in names if SequenceMatcher(None, normalized, " ".join(other.casefold().split())).ratio() >= .88]
        if name and matches:
            errors.append(f"{prefix}: nome identico o simile a {matches[0]}. Associa una variante oppure precisa il nome del nuovo articolo.")
        names.append(name)
        skus.add(sku.casefold())
        if barcode:
            barcodes.add(barcode.casefold())
    return errors


@transaction.atomic
def save_ocr_review(*, attachment, analysis_id, review):
    attachment = DocumentAttachment.objects.select_for_update().get(pk=attachment.pk)
    analysis = DocumentOcrAnalysis.objects.select_for_update().get(pk=analysis_id, attachment=attachment, status="SUCCEEDED")
    if analysis.proposed_data.get("review", {}).get("status") == "IMPORTED" or attachment.document.source_type == "GOODS_RECEIPT":
        raise ValidationError("La proposta è già stata importata e non è modificabile.")
    if not isinstance(review, dict) or not isinstance(review.get("items"), list) or any(not isinstance(item, dict) for item in review["items"]):
        raise ValidationError("La proposta deve contenere un elenco di righe valido.")
    review = dict(review, status="SAVED", conflicts=validate_ocr_review(review))
    review.pop("receipt_id", None)
    review.pop("imported_at", None)
    analysis.proposed_data = dict(analysis.proposed_data, review=review)
    analysis.save(update_fields=("proposed_data", "updated_at"))
    return analysis
