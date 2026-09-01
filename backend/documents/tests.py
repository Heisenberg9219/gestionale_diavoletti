import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import BusinessDocument, DocumentType
from .services import cancel_document, finalize_document


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
