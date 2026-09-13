from rest_framework import filters, serializers, viewsets
from django.db import transaction

from .permissions import IsBusinessOperator, IsOwner, IsOwnerOrClerk
from .viewsets import BusinessOperatorViewSet, OwnerWriteReadViewSet


COMMON_READ_ONLY = {
    "id", "created_at", "updated_at", "created_by", "updated_by",
    "status", "opened_at", "opened_by", "confirmed_at", "confirmed_by",
    "cancelled_at", "cancelled_by", "completed_at", "completed_by",
    "issued_at", "issued_by", "redeemed_at", "redeemed_by",
    "removed_at", "removed_by", "ordered_at", "ordered_by",
    "processed_at", "resolved_at", "resolved_by", "archived_at",
}

STATE_PARENTS = {
    "PurchaseOrderLine": "order", "GoodsReceiptLine": "receipt",
    "SupplierInvoiceLine": "invoice", "SupplierInvoiceReceipt": "invoice",
}
STATE_MODELS = {"PurchaseOrder", "GoodsReceipt", "SupplierInvoice", "Expense", "BusinessDocument", "GiftList"}


def check_editable(instance):
    parent_name = STATE_PARENTS.get(type(instance).__name__)
    parent = getattr(instance, parent_name) if parent_name else instance
    if type(parent).__name__ in STATE_MODELS:
        parent = type(parent).objects.select_for_update().get(pk=parent.pk)
        allowed = "OPEN" if type(parent).__name__ == "GiftList" else "DRAFT"
        if parent.status != allowed:
            raise serializers.ValidationError("Il documento non e' piu' modificabile nello stato corrente.")


def serializer_for(model, *, fully_read_only=False):
    model_fields = {field.name for field in model._meta.fields}
    read_only = model_fields if fully_read_only else model_fields & COMMON_READ_ONLY
    meta = type("Meta", (), {
        "model": model,
        "fields": "__all__",
        "read_only_fields": tuple(sorted(read_only)),
    })
    return type(f"{model.__name__}ApiSerializer", (serializers.ModelSerializer,), {"Meta": meta})


def viewset_for(model, *, mode="owner", read_only=False):
    serializer_class = serializer_for(model, fully_read_only=read_only)
    permission = {"owner": IsOwner, "operator": IsBusinessOperator, "read": IsOwnerOrClerk}[mode]
    base = viewsets.ReadOnlyModelViewSet if read_only else (
        BusinessOperatorViewSet if mode == "operator" else OwnerWriteReadViewSet
    )
    char_fields = tuple(
        field.name for field in model._meta.fields
        if field.get_internal_type() in {"CharField", "TextField", "EmailField"}
    )

    class GeneratedViewSet(base):
        queryset = model.objects.all()
        permission_classes = (permission,)
        filter_backends = (filters.SearchFilter, filters.OrderingFilter)
        search_fields = char_fields
        ordering_fields = tuple(field.name for field in model._meta.fields)

        def get_queryset(self):
            queryset = super().get_queryset().order_by("pk")
            if getattr(self, "swagger_fake_view", False):
                return queryset.none()
            ignored = {"page", "page_size", "search", "ordering"}
            concrete = {field.name for field in model._meta.fields}
            for key, value in self.request.query_params.items():
                if key not in ignored and key in concrete:
                    queryset = queryset.filter(**{key: value})
            return queryset

        @transaction.atomic
        def perform_create(self, serializer):
            values = {}
            fields = {field.name for field in model._meta.fields}
            for name in ("created_by", "updated_by"):
                if name in fields:
                    values[name] = self.request.user
            parent_name = STATE_PARENTS.get(model.__name__)
            if parent_name:
                check_editable(model(**serializer.validated_data))
            serializer.save(**values)

        @transaction.atomic
        def perform_update(self, serializer):
            check_editable(serializer.instance)
            parent_name = STATE_PARENTS.get(model.__name__)
            if parent_name and parent_name in serializer.validated_data:
                check_editable(model(**serializer.validated_data))
            values = {"updated_by": self.request.user} if hasattr(serializer.instance, "updated_by") else {}
            serializer.save(**values)

    GeneratedViewSet.serializer_class = serializer_class
    GeneratedViewSet.__name__ = f"{model.__name__}ApiViewSet"
    return GeneratedViewSet
