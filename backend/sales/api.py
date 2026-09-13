import csv

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.permissions import IsBusinessOperator
from api.viewsets import OwnerWriteReadViewSet
from catalog.models import ProductVariant
from giftlists.models import GiftListItem, ReservedStockSaleAuthorization
from .models import CashRegister, CashSession, Sale, SaleLine, SalePayment
from .serializers import CashRegisterSerializer, CashSessionSerializer, CloseCashSerializer, LineCommandSerializer, OpenCashSerializer, PaymentCommandSerializer, SaleLineSerializer, SalePaymentSerializer, SaleSerializer, TotalOverrideCommandSerializer
from .services import add_sale_payment, close_cash_session, confirm_sale, get_open_sale_stock_warning, open_cash_session, set_sale_line, set_sale_total_override
from .draft_services import remove_draft_line, remove_draft_payment, cancel_draft_sale
from .serializers import DraftReasonSerializer, RemoveLineSerializer, RemovePaymentSerializer
from api.factories import serializer_for
from .models import SaleDraftChange
from drf_spectacular.utils import extend_schema


class CashRegisterViewSet(OwnerWriteReadViewSet):
    queryset = CashRegister.objects.select_related("location"); serializer_class = CashRegisterSerializer


class CashSessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = CashSession.objects.select_related("cash_register", "opened_by", "closed_by"); serializer_class = CashSessionSerializer; permission_classes = (IsBusinessOperator,)
    @action(detail=False, methods=("post",))
    def open(self, request):
        data = OpenCashSerializer(data=request.data); data.is_valid(raise_exception=True)
        obj = open_cash_session(cash_register=get_object_or_404(CashRegister, pk=data.validated_data["cash_register"]), opened_by=request.user, opening_cash_amount=data.validated_data["opening_cash_amount"], notes=data.validated_data.get("notes", ""))
        return Response(self.get_serializer(obj).data, status=201)
    @action(detail=True, methods=("post",))
    def close(self, request, pk=None):
        data = CloseCashSerializer(data=request.data); data.is_valid(raise_exception=True)
        return Response(self.get_serializer(close_cash_session(cash_session=self.get_object(), counted_cash_amount=data.validated_data["counted_cash_amount"], closed_by=request.user)).data)


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.select_related("cash_session__cash_register", "customer", "location").prefetch_related("lines__variant__product__brand", "payments")
    serializer_class = SaleSerializer; permission_classes = (IsBusinessOperator,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = (
        "number", "customer__customer_code", "customer__first_name", "customer__last_name",
        "customer__children__first_name",
        "lines__variant__sku", "lines__variant__barcodes__code",
        "lines__variant__product__name", "lines__variant__product__brand__name",
    )
    ordering_fields = ("opened_at", "confirmed_at", "final_total_amount")

    def get_queryset(self):
        queryset = super().get_queryset()
        filters_by_parameter = {
            "status": "status",
            "channel": "channel",
            "location": "location_id",
            "cash_register": "cash_session__cash_register_id",
            "brand": "lines__variant__product__brand_id",
            "category": "lines__variant__product__category_id",
            "season": "lines__variant__product__season_id",
            "payment_method": "payments__method",
        }
        for parameter, field in filters_by_parameter.items():
            if value := self.request.query_params.get(parameter):
                queryset = queryset.filter(**{field: value})
        if value := self.request.query_params.get("date_from"):
            queryset = queryset.filter(confirmed_at__date__gte=value)
        if value := self.request.query_params.get("date_to"):
            queryset = queryset.filter(confirmed_at__date__lte=value)
        return queryset.distinct()

    @action(detail=False, methods=("get",), url_path="export-csv")
    def export_csv(self, request):
        """Download the same sales history currently selected by query parameters."""
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="vendite.csv"'
        response.write("\ufeff")
        csv_writer = csv.writer(response, delimiter=";")
        csv_writer.writerow((
            "Numero", "Data", "Stato", "Canale", "Sede", "Cassa", "Cliente",
            "Articolo", "Marca", "SKU", "Quantita", "Prezzo unitario", "Totale riga",
            "Totale scontrino", "Pagamenti",
        ))
        sales = self.filter_queryset(self.get_queryset())
        for sale in sales:
            common = (
                sale.number, (sale.confirmed_at or sale.opened_at).strftime("%d/%m/%Y %H:%M"),
                sale.get_status_display(), sale.get_channel_display(), sale.location.name,
                sale.cash_session.cash_register.name if sale.cash_session_id else "",
                sale.customer.full_name if sale.customer else "Vendita banco",
            )
            payment_methods = ", ".join(payment.get_method_display() for payment in sale.payments.all())
            lines = list(sale.lines.all())
            if not lines:
                csv_writer.writerow((*common, "", "", "", "", "", sale.final_total_amount, payment_methods))
                continue
            for line in lines:
                product = line.variant.product
                csv_writer.writerow((
                    *common, line.product_name_snapshot, product.brand.name if product.brand_id else "",
                    line.sku_snapshot, line.quantity, line.final_unit_price, line.net_amount,
                    sale.final_total_amount, payment_methods,
                ))
        return response
    def perform_create(self, serializer): serializer.save(opened_by=self.request.user)
    @extend_schema(request=RemoveLineSerializer)
    @action(detail=True, methods=("post",), url_path="remove-line")
    def remove_line(self, request, pk=None):
        data = RemoveLineSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sale = self.get_object()
        line = get_object_or_404(SaleLine, pk=data.validated_data["line"], sale=sale)
        remove_draft_line(sale=sale, line=line, removed_by=request.user, reason=data.validated_data["reason"])
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=RemovePaymentSerializer)
    @action(detail=True, methods=("post",), url_path="remove-payment")
    def remove_payment(self, request, pk=None):
        data = RemovePaymentSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sale = self.get_object()
        payment = get_object_or_404(SalePayment, pk=data.validated_data["payment"], sale=sale)
        remove_draft_payment(sale=sale, payment=payment, removed_by=request.user, reason=data.validated_data["reason"])
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=DraftReasonSerializer)
    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        data = DraftReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        sale = cancel_draft_sale(sale=self.get_object(), cancelled_by=request.user, reason=data.validated_data["reason"])
        return Response(self.get_serializer(sale).data)

    @extend_schema(responses=serializer_for(SaleDraftChange, fully_read_only=True)(many=True))
    @action(detail=True, methods=("get",), url_path="draft-changes")
    def draft_changes(self, request, pk=None):
        return Response(serializer_for(SaleDraftChange, fully_read_only=True)(self.get_object().draft_changes.all(), many=True).data)
    @transaction.atomic
    def perform_update(self, serializer):
        sale = Sale.objects.select_for_update().get(pk=serializer.instance.pk)
        if sale.status != Sale.Status.OPEN or sale.lines.exists() or sale.payments.exists():
            raise ValidationError("Usare le azioni operative: questa vendita contiene gia' righe o pagamenti oppure e' chiusa.")
        serializer.save()
    def destroy(self, request, *args, **kwargs): return Response({"detail": "Annullare la vendita invece di eliminarla."}, status=405)
    @action(detail=True, methods=("post",), url_path="set-line")
    def set_line(self, request, pk=None):
        data = LineCommandSerializer(data=request.data); data.is_valid(raise_exception=True); values = data.validated_data
        authorization = values.get("reserved_stock_authorization")
        gift_list_item = values.get("gift_list_item")
        line = set_sale_line(sale=self.get_object(), variant=get_object_or_404(ProductVariant, pk=values["variant"]), quantity=values["quantity"], manual_unit_price=values.get("manual_unit_price"), manual_override_reason=values.get("reason", ""), manual_override_by=request.user, reserved_stock_authorization=get_object_or_404(ReservedStockSaleAuthorization, pk=authorization) if authorization else None, gift_list_item=get_object_or_404(GiftListItem, pk=gift_list_item) if gift_list_item else None)
        return Response(SaleLineSerializer(line).data)
    @action(detail=True, methods=("post",), url_path="set-total")
    def set_total(self, request, pk=None):
        data = TotalOverrideCommandSerializer(data=request.data); data.is_valid(raise_exception=True)
        sale = set_sale_total_override(sale=self.get_object(), final_total_amount=data.validated_data["final_total_amount"], manual_override_reason=data.validated_data["reason"], manual_override_by=request.user)
        return Response(self.get_serializer(sale).data)
    @action(detail=True, methods=("post",), url_path="add-payment")
    def add_payment(self, request, pk=None):
        data = PaymentCommandSerializer(data=request.data); data.is_valid(raise_exception=True); values = data.validated_data
        obj = add_sale_payment(sale=self.get_object(), method=values["method"], amount=values["amount"], cash_received_amount=values.get("cash_received_amount"), transaction_reference=values.get("transaction_reference", ""), created_by=request.user)
        return Response(SalePaymentSerializer(obj).data, status=201)
    @action(detail=True, methods=("post",))
    def confirm(self, request, pk=None): return Response(self.get_serializer(confirm_sale(sale=self.get_object(), confirmed_by=request.user)).data)
    @action(detail=True, methods=("get",), url_path="stock-warning")
    def stock_warning(self, request, pk=None):
        variant = get_object_or_404(ProductVariant, pk=request.query_params.get("variant"))
        return Response(get_open_sale_stock_warning(variant=variant, location=self.get_object().location))


class SaleLineViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SaleLine.objects.select_related("sale", "variant"); serializer_class = SaleLineSerializer; permission_classes = (IsBusinessOperator,)
    @action(detail=True, methods=("get",), url_path="returnable-quantity")
    def returnable_quantity(self, request, pk=None):
        from returns.services import get_returnable_quantity
        line = self.get_object()
        return Response({"line": str(line.pk), "quantity": get_returnable_quantity(original_sale_line=line) if line.sale.status == Sale.Status.CONFIRMED else 0})


class SalePaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SalePayment.objects.select_related("sale", "created_by"); serializer_class = SalePaymentSerializer; permission_classes = (IsBusinessOperator,)
