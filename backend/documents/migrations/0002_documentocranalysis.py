# Generated manually for the Azure OCR audit trail.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentOcrAnalysis",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(choices=[("AZURE_DOCUMENT_INTELLIGENCE", "Azure Document Intelligence")], max_length=48)),
                ("model_id", models.CharField(default="prebuilt-invoice", max_length=96)),
                ("status", models.CharField(choices=[("PENDING", "In attesa"), ("SUCCEEDED", "Completata"), ("FAILED", "Fallita")], default="PENDING", max_length=16)),
                ("proposed_data", models.JSONField(blank=True, default=dict)),
                ("provider_response", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("analyzed_at", models.DateTimeField(blank=True, null=True)),
                ("attachment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ocr_analyses", to="documents.documentattachment")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_document_ocr_analyses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="documentocranalysis",
            index=models.Index(fields=["attachment", "status"], name="doc_ocr_attach_status_idx"),
        ),
    ]
