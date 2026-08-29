from django.db import migrations


def seed_initial_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    RoleMetadata = apps.get_model("accounts", "RoleMetadata")

    owner_group, _ = Group.objects.get_or_create(name="Titolare")
    clerk_group, _ = Group.objects.get_or_create(name="Commesso")

    RoleMetadata.objects.get_or_create(
        group=owner_group,
        defaults={
            "code": "OWNER",
            "description": "Accesso completo al gestionale.",
            "is_system": True,
            "is_active": True,
        },
    )

    RoleMetadata.objects.get_or_create(
        group=clerk_group,
        defaults={
            "code": "CLERK",
            "description": (
                "Vendite, operazioni di magazzino consentite, "
                "clienti e prenotazioni."
            ),
            "is_system": True,
            "is_active": True,
        },
    )


def remove_initial_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    RoleMetadata = apps.get_model("accounts", "RoleMetadata")

    RoleMetadata.objects.filter(
        code__in=["OWNER", "CLERK"]
    ).delete()

    Group.objects.filter(
        name__in=["Titolare", "Commesso"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_rolemetadata"),
    ]

    operations = [
        migrations.RunPython(
            seed_initial_roles,
            remove_initial_roles,
        ),
    ]