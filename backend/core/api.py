from rest_framework import filters, mixins, viewsets

from api.permissions import OwnerWriteClerkRead
from api.viewsets import OwnerWriteReadViewSet

from .models import Location, ShopSettings, TaxRate
from .serializers import LocationSerializer, ShopSettingsSerializer, TaxRateSerializer


class ShopSettingsViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ShopSettings.objects.all()
    serializer_class = ShopSettingsSerializer
    permission_classes = (OwnerWriteClerkRead,)


class LocationViewSet(OwnerWriteReadViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("code", "name", "address")
    ordering_fields = ("code", "name", "type", "created_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        if value := self.request.query_params.get("type"):
            queryset = queryset.filter(type=value)
        return queryset


class TaxRateViewSet(OwnerWriteReadViewSet):
    queryset = TaxRate.objects.all().order_by("code")
    serializer_class = TaxRateSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("code", "name")
    ordering_fields = ("code", "name", "percentage")
