import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from documents.models import BusinessDocument, DocumentAttachment, DocumentType


MEDIA_DIR = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_DIR)
class ProtectedAttachmentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_DIR, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="files-owner@example.com", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        kind = DocumentType.objects.create(code="FILES", name="Fattura", direction="INCOMING")
        cls.document = BusinessDocument.objects.create(
            document_type=kind, direction="INCOMING", document_date=date(2026, 9, 1),
            title="Fattura", created_by=cls.owner,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def upload(self, name, content):
        return self.client.post(
            f"/api/v1/documents/documents/{self.document.pk}/upload-attachment/",
            {"file": SimpleUploadedFile(name, content)},
            format="multipart",
        )

    def test_pdf_is_saved_with_random_name_and_downloaded_only_when_authenticated(self):
        response = self.upload("fattura cliente.pdf", b"%PDF-1.4 contenuto")
        self.assertEqual(response.status_code, 201, response.data)
        attachment = DocumentAttachment.objects.get(pk=response.data["id"])
        self.assertNotIn("fattura", attachment.file.name)
        self.assertTrue(attachment.file.name.endswith(".pdf"))
        self.assertEqual(attachment.original_name, "fattura cliente.pdf")

        download = self.client.get(f"/api/v1/documents/attachments/{attachment.pk}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4 contenuto")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")

        anonymous = APIClient()
        self.assertEqual(anonymous.get(f"/api/v1/documents/attachments/{attachment.pk}/download/").status_code, 401)

    def test_html_and_fake_pdf_are_rejected(self):
        self.assertEqual(self.upload("pagina.html", b"<script>alert(1)</script>").status_code, 400)
        self.assertEqual(self.upload("finto.pdf", b"<script>alert(1)</script>").status_code, 400)
        self.assertFalse(DocumentAttachment.objects.exists())

    @override_settings(MEDIA_USE_X_ACCEL_REDIRECT=True)
    def test_production_download_is_delegated_to_nginx(self):
        response = self.upload("fattura.pdf", b"%PDF-1.4")
        attachment = DocumentAttachment.objects.get(pk=response.data["id"])
        download = self.client.get(f"/api/v1/documents/attachments/{attachment.pk}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["X-Accel-Redirect"], f"/protected-media/{attachment.file.name}")
