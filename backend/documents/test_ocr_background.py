import shutil
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from documents import services
from documents.models import BusinessDocument, DocumentAttachment, DocumentOcrAnalysis, DocumentType

MEDIA_DIR = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_DIR)
class BackgroundOcrTests(TestCase):
    """L'OCR parte in background: la richiesta risponde subito."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_DIR, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="ocr-bg@example.com", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        kind = DocumentType.objects.create(code="OCR-BG", name="Fattura", direction="INCOMING")
        document = BusinessDocument.objects.create(document_type=kind, direction="INCOMING", document_date=date(2026, 9, 1), title="F", created_by=cls.owner)
        cls.attachment = DocumentAttachment.objects.create(
            document=document, original_name="f.pdf", uploaded_by=cls.owner,
            file=SimpleUploadedFile("f.pdf", b"%PDF-1.4 test"),
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def start(self):
        return self.client.post(f"/api/v1/documents/attachments/{self.attachment.pk}/analyze-invoice/", {}, format="json")

    @patch("documents.services._launch_analysis_thread")
    def test_request_returns_immediately_with_pending_analysis(self, launch):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.start()
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], "PENDING")
        launch.assert_called_once()
        # Una seconda richiesta non avvia un'altra analisi in parallelo.
        with self.captureOnCommitCallbacks(execute=True):
            again = self.start()
        self.assertEqual(again.data["id"], response.data["id"])
        launch.assert_called_once()

    @patch("documents.services._analyze_with_azure", side_effect=RuntimeError("Azure non raggiungibile"))
    @patch("documents.services._launch_analysis_thread", side_effect=lambda pk: services.process_invoice_analysis(pk))
    def test_background_result_is_saved_and_readable(self, launch, analyze):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.start()
        detail = self.client.get(f"/api/v1/documents/ocr-analyses/{response.data['id']}/")
        self.assertEqual(detail.data["status"], "FAILED")
        self.assertIn("non raggiungibile", detail.data["error_message"])

    @patch("documents.services._launch_analysis_thread")
    def test_stuck_analysis_is_closed_and_can_be_restarted(self, launch):
        stuck = DocumentOcrAnalysis.objects.create(attachment=self.attachment, provider="AZURE_DOCUMENT_INTELLIGENCE", requested_by=self.owner)
        DocumentOcrAnalysis.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        self.client.get("/api/v1/documents/ocr-analyses/")
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, "FAILED")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.start()
        self.assertNotEqual(response.data["id"], str(stuck.pk))

    def test_non_pdf_is_rejected(self):
        image = DocumentAttachment.objects.create(
            document=self.attachment.document, original_name="f.png", uploaded_by=self.owner,
            file=SimpleUploadedFile("f.png", b"\\x89PNG\\r\\n\\x1a\\n"),
        )
        response = self.client.post(f"/api/v1/documents/attachments/{image.pk}/analyze-invoice/", {}, format="json")
        self.assertEqual(response.status_code, 400)
