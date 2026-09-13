from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_seed_initial_roles"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPagePermission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_key", models.CharField(max_length=48)),
                ("can_view", models.BooleanField(default=False)),
                ("can_create", models.BooleanField(default=False)),
                ("can_update", models.BooleanField(default=False)),
                ("can_delete", models.BooleanField(default=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="page_permissions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("page_key",)},
        ),
        migrations.AddConstraint(
            model_name="userpagepermission",
            constraint=models.UniqueConstraint(fields=("user", "page_key"), name="accounts_user_page_permission_unique"),
        ),
    ]
