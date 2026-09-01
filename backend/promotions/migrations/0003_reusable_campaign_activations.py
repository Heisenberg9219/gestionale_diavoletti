import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def link_existing_applications(apps, schema_editor):
    Campaign = apps.get_model("promotions", "PromotionCampaign")
    Activation = apps.get_model(
        "promotions",
        "PromotionCampaignActivation",
    )
    Application = apps.get_model(
        "promotions",
        "SalePromotionApplication",
    )

    campaign_ids = (
        Application.objects.filter(activation__isnull=True)
        .values_list("offer__campaign_id", flat=True)
        .distinct()
    )

    for campaign in Campaign.objects.filter(id__in=campaign_ids):
        status = "ENABLED"
        if campaign.status == "ENDED":
            status = "ENDED"
        elif campaign.status == "CANCELLED":
            status = "CANCELLED"

        activation = Activation.objects.create(
            campaign=campaign,
            activation_number=1,
            status=status,
            valid_from=campaign.valid_from,
            valid_until=campaign.valid_until,
            configuration_snapshot={},
            enabled_by_id=campaign.created_by_id,
        )
        Application.objects.filter(
            activation__isnull=True,
            offer__campaign=campaign,
        ).update(activation=activation)


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0002_promotionrule_fixed_discount_scope"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="promotioncampaign",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="PromotionCampaignActivation",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activation_number", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ENABLED", "Abilitata"),
                            ("ENDED", "Terminata"),
                            ("CANCELLED", "Annullata"),
                        ],
                        default="ENABLED",
                        max_length=16,
                    ),
                ),
                ("valid_from", models.DateTimeField()),
                ("valid_until", models.DateTimeField()),
                ("configuration_snapshot", models.JSONField(default=dict)),
                ("enabled_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                (
                    "cancellation_reason",
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="activations",
                        to="promotions.promotioncampaign",
                    ),
                ),
                (
                    "enabled_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="enabled_promotion_activations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ended_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ended_promotion_activations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cancelled_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cancelled_promotion_activations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-valid_from",)},
        ),
        migrations.AddConstraint(
            model_name="promotioncampaignactivation",
            constraint=models.UniqueConstraint(
                fields=("campaign", "activation_number"),
                name="promo_campaign_activation_number_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="promotioncampaignactivation",
            constraint=models.CheckConstraint(
                condition=Q(valid_until__gt=F("valid_from")),
                name="promo_activation_dates_valid",
            ),
        ),
        migrations.AddField(
            model_name="salepromotionapplication",
            name="activation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_applications",
                to="promotions.promotioncampaignactivation",
            ),
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="sku_snapshot",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="product_code_snapshot",
            field=models.CharField(default="", max_length=48),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="product_name_snapshot",
            field=models.CharField(default="", max_length=160),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="category_code_snapshot",
            field=models.CharField(default="", max_length=48),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="category_name_snapshot",
            field=models.CharField(default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="brand_code_snapshot",
            field=models.CharField(blank=True, default="", max_length=48),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="brand_name_snapshot",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="season_code_snapshot",
            field=models.CharField(blank=True, default="", max_length=48),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="season_name_snapshot",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="salepromotionallocation",
            name="supplier_codes_snapshot",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(
            link_existing_applications,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="salepromotionapplication",
            name="activation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sale_applications",
                to="promotions.promotioncampaignactivation",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="promotioncampaign",
            name="promo_campaign_dates_valid",
        ),
        migrations.RemoveField(
            model_name="promotioncampaign",
            name="status",
        ),
        migrations.RemoveField(
            model_name="promotioncampaign",
            name="valid_from",
        ),
        migrations.RemoveField(
            model_name="promotioncampaign",
            name="valid_until",
        ),
        migrations.AlterModelOptions(
            name="promotioncampaign",
            options={"ordering": ("name",)},
        ),
    ]
