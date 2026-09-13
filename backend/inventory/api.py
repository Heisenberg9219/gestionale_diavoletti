import csv

from django.http import HttpResponse
from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.permissions import IsOwner, IsOwnerOrClerk
from catalog.models import ProductVariant
from core.models import Location
from .models import InventoryCountLine, InventoryCountSession, StockBalance, StockMovement, VariantInventoryCost
from .serializers import AdjustmentSerializer, CountQuantitySerializer, InventoryCountLineSerializer, InventoryCountSessionSerializer, StockBalanceSerializer, StockMovementSerializer, TransferSerializer, VariantInventoryCostSerializer
from .services import cancel_inventory_count, confirm_inventory_count, post_stock_movement, record_inventory_count, start_inventory_count, transfer_stock


class InventoryReadViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (IsOwnerOrClerk,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)


class StockBalanceViewSet(InventoryReadViewSet):
    queryset = StockBalance.objects.select_related("variant", "variant__product", "location")
    serializer_class = StockBalanceSerializer
    search_fields = ("variant__sku", "variant__product__name", "location__name")
    ordering_fields = ("quantity_on_hand", "updated_at")
    def get_queryset(self):
        queryset = super().get_queryset()
        if location := self.request.query_params.get("location"): queryset = queryset.filter(location_id=location)
        if variant := self.request.query_params.get("variant"): queryset = queryset.filter(variant_id=variant)
        if self.request.query_params.get("depleted") == "true": queryset = queryset.filter(quantity_on_hand=0)
        return queryset

    @action(detail=True, methods=("post",), permission_classes=(IsOwner,))
    def transfer(self, request, pk=None):
        balance = self.get_object(); data = TransferSerializer(data=request.data); data.is_valid(raise_exception=True)
        destination = get_object_or_404(Location, pk=data.validated_data["destination_location"])
        outgoing, incoming = transfer_stock(variant=balance.variant, source_location=balance.location, destination_location=destination, quantity=data.validated_data["quantity"], reference_number=data.validated_data.get("reference_number", ""), notes=data.validated_data.get("notes", ""), created_by=request.user)
        return Response({"outgoing": StockMovementSerializer(outgoing).data, "incoming": StockMovementSerializer(incoming).data})


class InventoryCostViewSet(InventoryReadViewSet):
    queryset = VariantInventoryCost.objects.select_related("variant", "variant__product"); serializer_class = VariantInventoryCostSerializer
    search_fields = ("variant__sku", "variant__product__name"); ordering_fields = ("inventory_value", "total_quantity", "weighted_average_unit_cost")


class StockMovementViewSet(InventoryReadViewSet):
    queryset = StockMovement.objects.select_related("variant", "location", "created_by"); serializer_class = StockMovementSerializer
    search_fields = ("variant__sku", "reference_number", "source_type"); ordering_fields = ("occurred_at", "quantity_delta", "unit_cost")
    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in (("variant", "variant_id"), ("location", "location_id"), ("type", "movement_type")):
            if value := self.request.query_params.get(parameter): queryset = queryset.filter(**{field: value})
        return queryset

    @action(detail=False, methods=("post",), permission_classes=(IsOwner,))
    def adjust(self, request):
        data = AdjustmentSerializer(data=request.data); data.is_valid(raise_exception=True); values = data.validated_data
        variant = get_object_or_404(ProductVariant, pk=values["variant"]); location = get_object_or_404(Location, pk=values["location"])
        delta = values["quantity_delta"]
        movement = post_stock_movement(variant=variant, location=location, movement_type=StockMovement.Type.ADJUSTMENT_IN if delta > 0 else StockMovement.Type.ADJUSTMENT_OUT, quantity_delta=delta, notes=values["reason"], created_by=request.user)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class InventoryCountSessionViewSet(viewsets.ModelViewSet):
    queryset = InventoryCountSession.objects.select_related("location", "created_by", "confirmed_by", "cancelled_by").prefetch_related("brands", "categories", "seasons", "products", "variants", "suppliers")
    serializer_class = InventoryCountSessionSerializer; permission_classes = (IsOwner,)
    filter_backends = (filters.SearchFilter, filters.OrderingFilter); search_fields = ("code", "name", "notes"); ordering_fields = ("created_at", "started_at", "confirmed_at")
    def perform_create(self, serializer): serializer.save(created_by=self.request.user)
    def perform_update(self, serializer):
        if self.get_object().status != InventoryCountSession.Status.DRAFT:
            raise ValidationError("Puoi modificare soltanto un inventario in bozza.")
        serializer.save()
    def destroy(self, request, *args, **kwargs):
        session = self.get_object()
        if session.status == InventoryCountSession.Status.CONFIRMED:
            raise ValidationError("Un inventario confermato non può essere eliminato: le rettifiche di magazzino devono restare tracciate.")
        self.perform_destroy(session)
        return Response(status=status.HTTP_204_NO_CONTENT)
    @action(detail=True, methods=("post",))
    def start(self, request, pk=None): return Response(self.get_serializer(start_inventory_count(session=self.get_object())).data)
    @action(detail=True, methods=("post",))
    def confirm(self, request, pk=None): return Response(self.get_serializer(confirm_inventory_count(session=self.get_object(), confirmed_by=request.user)).data)
    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None): return Response(self.get_serializer(cancel_inventory_count(session=self.get_object(), cancelled_by=request.user)).data)
    @action(detail=True, methods=("post",))
    def duplicate(self, request, pk=None):
        original = self.get_object()
        code = request.data.get("code") or f"{original.code}-COPIA"
        name = request.data.get("name") or f"{original.name} (copia)"
        with transaction.atomic():
            if InventoryCountSession.objects.filter(code=code).exists():
                raise ValidationError({"code": "Esiste già un inventario con questo codice."})
            duplicate = InventoryCountSession.objects.create(
                code=code,
                name=name,
                location=original.location,
                scope=original.scope,
                notes=original.notes,
                created_by=request.user,
            )
            duplicate.brands.set(original.brands.all())
            duplicate.categories.set(original.categories.all())
            duplicate.seasons.set(original.seasons.all())
            duplicate.products.set(original.products.all())
            duplicate.variants.set(original.variants.all())
            duplicate.suppliers.set(original.suppliers.all())
        return Response(self.get_serializer(duplicate).data, status=status.HTTP_201_CREATED)
    @action(detail=True, methods=("get",), url_path="export-csv")
    def export_csv(self, request, pk=None):
        session = self.get_object()
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{session.code}.csv"'
        response.write("\ufeff")
        rows = csv.writer(response, delimiter=";")
        rows.writerow(("Inventario", "Sede", "SKU", "Articolo", "Previsto", "Contato", "Differenza", "Note"))
        for line in session.lines.select_related("variant__product"):
            rows.writerow((session.name, session.location.name, line.variant.sku, line.variant.product.name, line.expected_quantity, line.counted_quantity if line.counted_quantity is not None else "", line.difference_quantity if line.counted_quantity is not None else "", line.notes))
        return response


class InventoryCountLineViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = InventoryCountLine.objects.select_related("session", "variant", "variant__product", "counted_by", "adjustment_movement")
    serializer_class = InventoryCountLineSerializer; permission_classes = (IsOwner,)
    def get_queryset(self):
        queryset = super().get_queryset()
        if session := self.request.query_params.get("session"): queryset = queryset.filter(session_id=session)
        return queryset
    @action(detail=True, methods=("post",))
    def count(self, request, pk=None):
        data = CountQuantitySerializer(data=request.data); data.is_valid(raise_exception=True)
        line = record_inventory_count(line=self.get_object(), counted_quantity=data.validated_data["counted_quantity"], counted_by=request.user, notes=data.validated_data.get("notes"))
        return Response(self.get_serializer(line).data)
