from rest_framework import filters

from api.viewsets import OwnerWriteReadViewSet

from .models import Supplier, SupplierVariant
from .serializers import SupplierSerializer, SupplierVariantSerializer


class SupplierViewSet(OwnerWriteReadViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("code", "business_name", "vat_number", "tax_code", "email", "phone")
    ordering_fields = ("code", "business_name", "city", "created_at")


class SupplierVariantViewSet(OwnerWriteReadViewSet):
    queryset = SupplierVariant.objects.select_related("supplier", "variant", "variant__product")
    serializer_class = SupplierVariantSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("supplier__business_name", "supplier_product_code", "variant__sku", "variant__product__name")
    ordering_fields = ("supplier", "variant", "minimum_order_quantity", "lead_time_days")

    def get_queryset(self):
        queryset = super().get_queryset()
        if supplier := self.request.query_params.get("supplier"):
            queryset = queryset.filter(supplier_id=supplier)
        if variant := self.request.query_params.get("variant"):
            queryset = queryset.filter(variant_id=variant)
        if self.request.query_params.get("preferred") == "true":
            queryset = queryset.filter(is_preferred=True)
        return queryset
