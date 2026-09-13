from rest_framework import filters, mixins, viewsets

from api.permissions import IsBusinessOperator, OwnerWriteClerkRead
from api.viewsets import BusinessOperatorViewSet, OwnerWriteReadViewSet
from .models import ConsentPurpose, Customer, CustomerChild, CustomerConsentEvent
from .serializers import ConsentPurposeSerializer, CustomerChildSerializer, CustomerConsentEventSerializer, CustomerSerializer
from .services import record_consent_event


class CustomerViewSet(BusinessOperatorViewSet):
    queryset = Customer.objects.all(); serializer_class = CustomerSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("customer_code", "first_name", "last_name", "email", "phone")
    ordering_fields = ("customer_code", "first_name", "last_name", "created_at")
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)
    def perform_create(self, serializer): serializer.save(created_by=self.request.user)


class CustomerChildViewSet(BusinessOperatorViewSet):
    queryset = CustomerChild.objects.select_related("customer"); serializer_class = CustomerChildSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("first_name", "customer__customer_code", "customer__first_name", "customer__last_name")
    ordering_fields = ("first_name", "birth_date", "created_at")
    def get_queryset(self):
        queryset = super().get_queryset()
        if customer := self.request.query_params.get("customer"): queryset = queryset.filter(customer_id=customer)
        return queryset


class ConsentPurposeViewSet(OwnerWriteReadViewSet):
    queryset = ConsentPurpose.objects.all(); serializer_class = ConsentPurposeSerializer
    filter_backends = (filters.SearchFilter,); search_fields = ("code", "name", "description")


class CustomerConsentEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = CustomerConsentEvent.objects.select_related("customer", "purpose", "collected_by")
    serializer_class = CustomerConsentEventSerializer
    permission_classes = (IsBusinessOperator,)
    filter_backends = (filters.OrderingFilter,); ordering_fields = ("occurred_at", "created_at")
    def get_queryset(self):
        queryset = super().get_queryset()
        if customer := self.request.query_params.get("customer"): queryset = queryset.filter(customer_id=customer)
        if purpose := self.request.query_params.get("purpose"): queryset = queryset.filter(purpose_id=purpose)
        return queryset
    def perform_create(self, serializer):
        data = serializer.validated_data
        event = record_consent_event(
            customer=data["customer"], purpose=data["purpose"], action=data["action"],
            channel=data["channel"], collected_by=self.request.user,
            ip_address=self.request.META.get("REMOTE_ADDR"),
            user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
            related_event=data.get("related_event"),
        )
        serializer.instance = event
