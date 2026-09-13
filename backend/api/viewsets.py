from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response

from .permissions import IsBusinessOperator, OwnerWriteClerkRead


class OwnerWriteReadViewSet(viewsets.ModelViewSet):
    permission_classes = (OwnerWriteClerkRead,)
    filter_backends = ()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        update_fields = []
        if hasattr(instance, "is_active"):
            instance.is_active = False
            update_fields.append("is_active")
        if hasattr(instance, "archived_at"):
            instance.archived_at = timezone.now()
            update_fields.append("archived_at")
        if not update_fields:
            return Response(
                {"detail": "Questa risorsa non può essere eliminata."},
                status=status.HTTP_405_METHOD_NOT_ALLOWED,
            )
        if hasattr(instance, "updated_at"):
            update_fields.append("updated_at")
        instance.save(update_fields=update_fields)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BusinessOperatorViewSet(OwnerWriteReadViewSet):
    permission_classes = (IsBusinessOperator,)
