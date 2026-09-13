from django.db import transaction
from django.utils import timezone
from rest_framework import filters

from api.viewsets import OwnerWriteReadViewSet
from .models import VariantSalePrice
from .serializers import VariantSalePriceSerializer


class VariantSalePriceViewSet(OwnerWriteReadViewSet):
    queryset = VariantSalePrice.objects.select_related("variant", "variant__product", "created_by")
    serializer_class = VariantSalePriceSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("variant__sku", "variant__product__name", "notes")
    ordering_fields = ("valid_from", "valid_until", "amount", "created_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        if variant := self.request.query_params.get("variant"):
            queryset = queryset.filter(variant_id=variant)
        if self.request.query_params.get("current") == "true":
            now = timezone.now()
            queryset = queryset.filter(valid_from__lte=now, valid_until__isnull=True)
        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        variant = serializer.validated_data["variant"]
        valid_from = serializer.validated_data.get("valid_from", timezone.now())
        VariantSalePrice.objects.select_for_update().filter(
            variant=variant, valid_until__isnull=True
        ).update(valid_until=valid_from)
        serializer.save(created_by=self.request.user)
