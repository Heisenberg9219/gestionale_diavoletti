from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import UUIDTimeStampedModel


class ReportDashboard(UUIDTimeStampedModel):
    code = models.CharField(max_length=48, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_report_dashboards")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_report_dashboards")

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class ReportWidget(UUIDTimeStampedModel):
    class Visualization(models.TextChoices):
        KPI = "KPI", "Valore"
        LINE = "LINE", "Linea"
        BAR = "BAR", "Istogramma"
        PIE = "PIE", "Torta"
        TABLE = "TABLE", "Tabella"

    class Metric(models.TextChoices):
        REVENUE = "REVENUE", "Incassi"
        SALES = "SALES", "Numero vendite"
        UNITS = "UNITS", "Articoli venduti"
        DISCOUNTS = "DISCOUNTS", "Sconti"
        GROSS_MARGIN = "GROSS_MARGIN", "Margine stimato"
        RETURNS = "RETURNS", "Resi"
        INVENTORY_VALUE = "INVENTORY_VALUE", "Valore magazzino"
        INVENTORY_VARIANCE = "INVENTORY_VARIANCE", "Differenze inventariali"

    class Period(models.TextChoices):
        TODAY = "TODAY", "Oggi"
        THIS_WEEK = "THIS_WEEK", "Questa settimana"
        THIS_MONTH = "THIS_MONTH", "Questo mese"
        LAST_30_DAYS = "LAST_30_DAYS", "Ultimi 30 giorni"
        THIS_YEAR = "THIS_YEAR", "Anno corrente"
        CUSTOM = "CUSTOM", "Periodo personalizzato"

    class GroupBy(models.TextChoices):
        NONE = "NONE", "Nessuno"
        DAY = "DAY", "Giorno"
        WEEK = "WEEK", "Settimana"
        MONTH = "MONTH", "Mese"
        CHANNEL = "CHANNEL", "Canale"
        BRAND = "BRAND", "Marca"
        CATEGORY = "CATEGORY", "Categoria"
        PROMOTION = "PROMOTION", "Promozione"

    dashboard = models.ForeignKey(ReportDashboard, on_delete=models.CASCADE, related_name="widgets")
    title = models.CharField(max_length=160)
    visualization = models.CharField(max_length=16, choices=Visualization.choices)
    metric = models.CharField(max_length=32, choices=Metric.choices)
    period = models.CharField(max_length=24, choices=Period.choices)
    group_by = models.CharField(max_length=24, choices=GroupBy.choices, default=GroupBy.NONE)
    custom_date_from = models.DateField(null=True, blank=True)
    custom_date_to = models.DateField(null=True, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    compare_previous_period = models.BooleanField(default=False)
    auto_refresh_daily = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)
    width = models.PositiveSmallIntegerField(default=1)
    height = models.PositiveSmallIntegerField(default=1)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_report_widgets")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_report_widgets")

    class Meta:
        ordering = ("dashboard", "position", "created_at")
        constraints = [
            models.CheckConstraint(condition=Q(width__gt=0, height__gt=0), name="report_widget_dimensions_positive"),
            models.CheckConstraint(
                condition=(Q(period="CUSTOM", custom_date_from__isnull=False, custom_date_to__isnull=False, custom_date_to__gte=models.F("custom_date_from")) | (~Q(period="CUSTOM") & Q(custom_date_from__isnull=True, custom_date_to__isnull=True))),
                name="report_widget_custom_dates_valid",
            ),
        ]

    def __str__(self):
        return self.title


class ReportSnapshot(UUIDTimeStampedModel):
    widget = models.ForeignKey(ReportWidget, on_delete=models.CASCADE, related_name="snapshots")
    snapshot_date = models.DateField()
    period_from = models.DateField()
    period_to = models.DateField()
    result = models.JSONField(default=dict)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="generated_report_snapshots")

    class Meta:
        ordering = ("-snapshot_date",)
        constraints = [models.UniqueConstraint(fields=("widget", "snapshot_date"), name="report_widget_daily_snapshot_unique")]


class ReportExport(UUIDTimeStampedModel):
    class Format(models.TextChoices):
        CSV = "CSV", "CSV"
        XLSX = "XLSX", "Excel"

    class Status(models.TextChoices):
        PENDING = "PENDING", "In attesa"
        COMPLETED = "COMPLETED", "Completata"
        FAILED = "FAILED", "Fallita"

    widget = models.ForeignKey(ReportWidget, on_delete=models.PROTECT, related_name="exports")
    export_format = models.CharField(max_length=8, choices=Format.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="report_exports")
    completed_at = models.DateTimeField(null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
