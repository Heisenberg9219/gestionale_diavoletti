from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from sales.models import Sale, SaleLine

from .models import ReportSnapshot, ReportWidget


def ensure_reporting_access(user):
    if not user or not user.is_active or not (user.is_superuser or user.groups.filter(name="Titolare").exists()):
        raise PermissionDenied("La reportistica è riservata al titolare.")


def resolve_period(widget, today=None):
    today = today or timezone.localdate()
    if widget.period == ReportWidget.Period.TODAY:
        return today, today
    if widget.period == ReportWidget.Period.THIS_WEEK:
        return today - timedelta(days=today.weekday()), today
    if widget.period == ReportWidget.Period.THIS_MONTH:
        return today.replace(day=1), today
    if widget.period == ReportWidget.Period.LAST_30_DAYS:
        return today - timedelta(days=29), today
    if widget.period == ReportWidget.Period.THIS_YEAR:
        return today.replace(month=1, day=1), today
    if not widget.custom_date_from or not widget.custom_date_to:
        raise ValidationError("Il periodo personalizzato richiede entrambe le date.")
    return widget.custom_date_from, widget.custom_date_to


def _sales_queryset(date_from, date_to, filters):
    queryset = Sale.objects.filter(status=Sale.Status.CONFIRMED, confirmed_at__date__range=(date_from, date_to))
    if filters.get("channel"):
        queryset = queryset.filter(channel__in=filters["channel"])
    if filters.get("location_ids"):
        queryset = queryset.filter(location_id__in=filters["location_ids"])
    return queryset


def calculate_widget(widget, today=None):
    date_from, date_to = resolve_period(widget, today=today)
    sales = _sales_queryset(date_from, date_to, widget.filters)
    if widget.metric == ReportWidget.Metric.SALES:
        value = sales.count()
    elif widget.metric == ReportWidget.Metric.REVENUE:
        value = sales.aggregate(value=Sum("final_total_amount"))["value"] or Decimal("0.00")
    elif widget.metric == ReportWidget.Metric.DISCOUNTS:
        value = sales.aggregate(value=Sum("discount_amount"))["value"] or Decimal("0.00")
    elif widget.metric == ReportWidget.Metric.GROSS_MARGIN:
        totals = sales.aggregate(revenue=Sum("final_total_amount"), cost=Sum("total_cost_amount"))
        value = (totals["revenue"] or Decimal("0.00")) - (totals["cost"] or Decimal("0.00"))
    elif widget.metric == ReportWidget.Metric.UNITS:
        value = SaleLine.objects.filter(sale__in=sales).aggregate(value=Sum("quantity"))["value"] or 0
    else:
        raise ValidationError("Questa metrica sarà calcolata dal relativo modulo di report.")

    result = {"value": str(value), "date_from": str(date_from), "date_to": str(date_to), "series": []}
    if widget.group_by in (ReportWidget.GroupBy.DAY, ReportWidget.GroupBy.WEEK, ReportWidget.GroupBy.MONTH):
        trunc = {ReportWidget.GroupBy.DAY: TruncDay, ReportWidget.GroupBy.WEEK: TruncWeek, ReportWidget.GroupBy.MONTH: TruncMonth}[widget.group_by]
        grouped = sales.annotate(bucket=trunc("confirmed_at")).values("bucket").annotate(value=Sum("final_total_amount")).order_by("bucket")
        result["series"] = [{"label": row["bucket"].date().isoformat(), "value": str(row["value"])} for row in grouped]
    elif widget.group_by == ReportWidget.GroupBy.CHANNEL:
        grouped = sales.values("channel").annotate(value=Sum("final_total_amount")).order_by("channel")
        result["series"] = [{"label": row["channel"], "value": str(row["value"])} for row in grouped]
    return result


@transaction.atomic
def refresh_widget(widget, user=None, today=None):
    if user is not None:
        ensure_reporting_access(user)
    result = calculate_widget(widget, today=today)
    snapshot_date = today or timezone.localdate()
    snapshot, _ = ReportSnapshot.objects.update_or_create(
        widget=widget, snapshot_date=snapshot_date,
        defaults={"period_from": result["date_from"], "period_to": result["date_to"], "result": result, "generated_by": user},
    )
    widget.last_refreshed_at = timezone.now()
    widget.save(update_fields=("last_refreshed_at", "updated_at"))
    return snapshot
