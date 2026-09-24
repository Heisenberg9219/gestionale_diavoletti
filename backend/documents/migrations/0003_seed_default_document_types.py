from django.db import migrations


DEFAULT_DOCUMENT_TYPES = (
    {
        "code": "PURCHASE_INVOICE",
        "name": "Fattura di acquisto",
        "direction": "INCOMING",
        "requires_number": False,
    },
    {
        "code": "SALES_INVOICE",
        "name": "Fattura di vendita",
        "direction": "OUTGOING",
        "requires_number": False,
    },
    {
        "code": "INTERNAL_DOCUMENT",
        "name": "Documento interno",
        "direction": "INTERNAL",
        "requires_number": False,
    },
)


def seed_default_document_types(apps, schema_editor):
    DocumentType = apps.get_model("documents", "DocumentType")
    for values in DEFAULT_DOCUMENT_TYPES:
        DocumentType.objects.get_or_create(code=values["code"], defaults=values)


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_documentocranalysis"),
    ]

    operations = [
        migrations.RunPython(seed_default_document_types, migrations.RunPython.noop),
    ]
