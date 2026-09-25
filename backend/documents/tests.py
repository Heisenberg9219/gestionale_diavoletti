import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from unittest.mock import patch

from .models import BusinessDocument, DocumentAttachment, DocumentOcrAnalysis, DocumentType
from .services import (
    apply_ocr_purchase_proposal,
    save_ocr_purchase_proposal,
    analyze_invoice_attachment_with_azure,
    cancel_document,
    finalize_document,
)


class DocumentServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="documents-test@example.com",
            password="test-password",
        )
        cls.outgoing_type = DocumentType.objects.create(
            code="COMMERCIAL_DOC",
            name="Documento commerciale",
            direction=DocumentType.Direction.OUTGOING,
            automatic_numbering=True,
            number_prefix="DC",
        )
        cls.incoming_type = DocumentType.objects.create(
            code="SUPPLIER_CREDIT_NOTE",
            name="Nota di credito fornitore",
            direction=DocumentType.Direction.INCOMING,
        )

    def create_document(self, *, document_type=None, direction=None, **kwargs):
        document_type = document_type or self.outgoing_type
        return BusinessDocument.objects.create(
            document_type=document_type,
            direction=direction or document_type.direction,
            document_date=date(2026, 9, 1),
            title="Documento di prova",
            taxable_amount="100.00",
            tax_amount="22.00",
            total_amount="122.00",
            created_by=self.user,
            **kwargs,
        )

    def test_automatic_numbering_is_progressive(self):
        first = finalize_document(
            document=self.create_document(),
            finalized_by=self.user,
        )
        second = finalize_document(
            document=self.create_document(),
            finalized_by=self.user,
        )

        self.assertEqual(first.number, "DC-2026-000001")
        self.assertEqual(second.number, "DC-2026-000002")
        self.assertEqual(first.status, BusinessDocument.Status.ISSUED)
        self.assertIsNotNone(first.issued_at)

    def test_incoming_document_is_registered_with_manual_number(self):
        document = self.create_document(document_type=self.incoming_type)
        document = finalize_document(
            document=document,
            finalized_by=self.user,
            number="NC-44",
        )

        self.assertEqual(document.status, BusinessDocument.Status.REGISTERED)
        self.assertEqual(document.number, "NC-44")
        self.assertIsNotNone(document.registered_at)
        self.assertIsNone(document.issued_at)

    def test_required_manual_number_cannot_be_omitted(self):
        document = self.create_document(document_type=self.incoming_type)
        with self.assertRaises(ValidationError):
            finalize_document(document=document, finalized_by=self.user)

    def test_direction_must_match_document_type(self):
        document = self.create_document(
            document_type=self.incoming_type,
            direction=DocumentType.Direction.OUTGOING,
        )
        with self.assertRaises(ValidationError):
            finalize_document(
                document=document,
                finalized_by=self.user,
                number="NC-45",
            )

    def test_source_type_and_id_must_be_supplied_together(self):
        document = BusinessDocument(
            document_type=self.outgoing_type,
            direction=self.outgoing_type.direction,
            document_date=date(2026, 9, 1),
            title="Documento con origine incompleta",
            taxable_amount="100.00",
            tax_amount="22.00",
            total_amount="122.00",
            source_type="sales.Sale",
            created_by=self.user,
        )
        with self.assertRaises(ValidationError):
            document.full_clean()

        document.source_id = uuid.uuid4()
        document.full_clean()

    def test_document_totals_must_match(self):
        document = self.create_document()
        document.total_amount = Decimal("120.00")
        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_cancellation_is_traced_and_status_history_is_immutable(self):
        document = finalize_document(
            document=self.create_document(),
            finalized_by=self.user,
        )
        cancel_document(
            document=document,
            cancelled_by=self.user,
            reason="Documento emesso per errore",
        )

        document.refresh_from_db()
        self.assertEqual(document.status, BusinessDocument.Status.CANCELLED)
        self.assertEqual(document.status_changes.count(), 2)
        change = document.status_changes.order_by("created_at").last()
        self.assertEqual(change.new_status, BusinessDocument.Status.CANCELLED)
        change.reason = "Modifica vietata"
        with self.assertRaises(ValidationError):
            change.save()
        with self.assertRaises(ValidationError):
            change.delete()

    def test_automatic_numbering_is_rejected_for_incoming_type(self):
        document_type = DocumentType(
            code="INVALID_AUTO",
            name="Tipo non valido",
            direction=DocumentType.Direction.INCOMING,
            automatic_numbering=True,
        )
        with self.assertRaises(ValidationError):
            document_type.full_clean()


class AzureInvoiceOcrTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="ocr-test@example.com",
            password="test-password",
        )
        cls.document_type = DocumentType.objects.create(
            code="OCR_INVOICE",
            name="Fattura OCR",
            direction=DocumentType.Direction.INCOMING,
        )

    def setUp(self):
        self.document = BusinessDocument.objects.create(
            document_type=self.document_type,
            direction=DocumentType.Direction.INCOMING,
            document_date=date(2026, 9, 1),
            title="Fattura da analizzare",
            taxable_amount="0.00",
            tax_amount="0.00",
            total_amount="0.00",
            created_by=self.user,
        )
        self.attachment = DocumentAttachment.objects.create(
            document=self.document,
            original_name="fattura.pdf",
            file=SimpleUploadedFile("fattura.pdf", b"%PDF-1.4 test"),
            uploaded_by=self.user,
        )

    @patch("documents.services._analyze_with_azure")
    def test_successful_analysis_stores_editable_proposal(self, analyze):
        class Field:
            def __init__(self, value, confidence=0.99):
                self.value = value
                self.confidence = confidence

        class Result:
            def __init__(self):
                self.documents = [type("Document", (), {"fields": {
                    "VendorName": Field("Fornitore S.r.l."),
                    "InvoiceId": Field("FT-2026-10"),
                    "InvoiceDate": Field(date(2026, 9, 1)),
                    "SubTotal": Field("100.00"),
                    "TotalTax": Field("22.00"),
                    "InvoiceTotal": Field("122.00"),
                    "Items": Field([]),
                }})()]

            def as_dict(self):
                return {"status": "succeeded"}

        analyze.return_value = Result()

        analysis = analyze_invoice_attachment_with_azure(
            attachment=self.attachment,
            requested_by=self.user,
        )

        self.assertEqual(analysis.status, DocumentOcrAnalysis.Status.SUCCEEDED)
        self.assertEqual(analysis.proposed_data["invoice_number"], "FT-2026-10")
        self.assertEqual(analysis.proposed_data["total_amount"], "122.00")
        self.assertEqual(analysis.provider_response, {"status": "succeeded"})

    @patch("documents.services._analyze_with_azure", side_effect=RuntimeError("Azure non raggiungibile"))
    def test_failed_analysis_is_traced(self, analyze):
        analysis = analyze_invoice_attachment_with_azure(
            attachment=self.attachment,
            requested_by=self.user,
        )

        self.assertEqual(analysis.status, DocumentOcrAnalysis.Status.FAILED)
        self.assertIn("non raggiungibile", analysis.error_message)


class OcrPurchaseRegistrationTests(TestCase):
    def setUp(self):
        from catalog.models import Category, Product, ProductVariant, Size, SizeScale
        from core.models import Location, TaxRate

        self.user = get_user_model().objects.create_user(email="ocr-register@example.com", password="test-password")
        self.document_type = DocumentType.objects.create(code="OCR_PURCHASE", name="Fattura OCR acquisto", direction=DocumentType.Direction.INCOMING)
        tax_rate = TaxRate.objects.create(code="OCR_PURCHASE_VAT", name="IVA OCR", percentage="22.00")
        category = Category.objects.create(code="OCR_PURCHASE_CATEGORY", name="Categoria OCR")
        scale = SizeScale.objects.create(code="OCR_PURCHASE_SCALE", name="Scala OCR", scale_type=SizeScale.Type.ONE_SIZE)
        size = Size.objects.create(size_scale=scale, code="ONE", label="Unica")
        product = Product.objects.create(code="OCR_PURCHASE_PRODUCT", name="Prodotto OCR", category=category, tax_rate=tax_rate)
        self.variant = ProductVariant.objects.create(product=product, sku="OCR-PURCHASE-SKU", size=size)
        self.location = Location.objects.create(code="OCR_PURCHASE_LOCATION", name="Magazzino OCR", type=Location.Type.STOCKROOM)
        self.document = BusinessDocument.objects.create(document_type=self.document_type, direction=DocumentType.Direction.INCOMING, document_date=date(2026, 9, 1), title="Da OCR", taxable_amount="0.00", tax_amount="0.00", total_amount="0.00", created_by=self.user)
        attachment = DocumentAttachment.objects.create(document=self.document, original_name="fattura.pdf", file=SimpleUploadedFile("fattura.pdf", b"%PDF"), uploaded_by=self.user)
        self.analysis = DocumentOcrAnalysis.objects.create(attachment=attachment, provider=DocumentOcrAnalysis.Provider.AZURE_DOCUMENT_INTELLIGENCE, status=DocumentOcrAnalysis.Status.SUCCEEDED, proposed_data={"supplier_vat_number": "IT12345678901"})

    def test_approved_proposal_registers_invoice_and_loads_stock(self):
        result = apply_ocr_purchase_proposal(
            analysis=self.analysis,
            applied_by=self.user,
            location_id=self.location.pk,
            review={"supplier_name": "Fornitore OCR", "invoice_number": "FT-42", "invoice_date": "2026-09-01", "tax_rate": "22", "items": [{"accepted": True, "description": "Prodotto OCR", "variant_id": str(self.variant.pk), "quantity": "3", "unit_price": "10.00"}]},
        )
        from inventory.models import StockBalance
        from purchasing.models import GoodsReceipt, SupplierInvoice

        self.document.refresh_from_db(); self.analysis.refresh_from_db()
        self.assertEqual(self.document.status, BusinessDocument.Status.REGISTERED)
        self.assertEqual(self.document.number, "FT-42")
        self.assertEqual(self.document.total_amount, Decimal("36.60"))
        self.assertEqual(StockBalance.objects.get(variant=self.variant, location=self.location).quantity_on_hand, 3)
        self.assertEqual(result["receipt"].status, GoodsReceipt.Status.CONFIRMED)
        self.assertEqual(result["invoice"].status, SupplierInvoice.Status.CONFIRMED)
        self.assertEqual(self.analysis.proposed_data["review"]["status"], "APPLIED")

    def test_review_draft_is_preserved_without_posting_stock(self):
        save_ocr_purchase_proposal(
            analysis=self.analysis, saved_by=self.user,
            review={"supplier_name": "Fornitore OCR", "invoice_number": "FT-BOZZA", "items": [{"accepted": True, "description": "Da associare", "variant_id": "", "quantity": "2", "unit_price": "8.00"}]},
        )
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.proposed_data["review"]["status"], "DRAFT")
        self.assertEqual(self.analysis.proposed_data["review"]["items"][0]["description"], "Da associare")

    def test_new_product_can_split_the_ocr_quantity_across_sizes(self):
        from catalog.models import ProductBarcode, Size
        from inventory.models import StockBalance
        from pricing.models import VariantSalePrice

        other_size = Size.objects.create(
            size_scale=self.variant.size.size_scale, code="M", label="M",
        )
        apply_ocr_purchase_proposal(
            analysis=self.analysis, applied_by=self.user, location_id=self.location.pk,
            review={"supplier_name": "Fornitore OCR", "invoice_number": "FT-TAGLIE", "invoice_date": "2026-09-01", "tax_rate": "22", "items": [{
                "accepted": True, "description": "Nuovo articolo", "variant_id": "",
                "quantity": "3", "unit_price": "10.00", "new_variant": {
                    "product_name": "Nuovo articolo", "category_id": str(self.variant.product.category_id),
                    "color_id": "", "variants": [
                        {"sku": "TEST-S", "barcode": "1234567890123", "size_id": str(self.variant.size_id), "quantity": "1", "sale_price": "19.90"},
                        {"sku": "TEST-M", "size_id": str(other_size.pk), "quantity": "2", "sale_price": "19.90"},
                    ],
                },
            }]},
        )
        self.assertEqual(StockBalance.objects.get(variant__sku="TEST-S", location=self.location).quantity_on_hand, 1)
        self.assertEqual(StockBalance.objects.get(variant__sku="TEST-M", location=self.location).quantity_on_hand, 2)
        self.assertEqual(VariantSalePrice.objects.filter(variant__sku__in=("TEST-S", "TEST-M"), amount="19.90").count(), 2)
        self.assertTrue(ProductBarcode.objects.filter(variant__sku="TEST-S", code="1234567890123").exists())
