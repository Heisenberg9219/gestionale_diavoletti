from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import GoodsReceipt, SupplierInvoice, SupplierInvoiceReceipt


class InvoiceReceiptsSerializer(serializers.Serializer):
    receipts = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)


def invoice_receipt_actions(base):
    @extend_schema(request=InvoiceReceiptsSerializer)
    @action(detail=True, methods=("post",), url_path="set-receipts")
    @transaction.atomic
    def set_receipts(self, request, pk=None):
        data = InvoiceReceiptsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invoice = SupplierInvoice.objects.select_for_update().get(pk=self.get_object().pk)
        if invoice.status != SupplierInvoice.Status.DRAFT:
            raise serializers.ValidationError("La fattura non e' in bozza.")
        ids = set(data.validated_data["receipts"])
        receipts = list(GoodsReceipt.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        if len(receipts) != len(ids):
            raise serializers.ValidationError("Uno o piu' ricevimenti non esistono.")
        if any(receipt.supplier_id != invoice.supplier_id or receipt.status != GoodsReceipt.Status.CONFIRMED for receipt in receipts):
            raise serializers.ValidationError("Servono ricevimenti confermati dello stesso fornitore.")
        used_ids = set(invoice.lines.exclude(receipt_line=None).values_list("receipt_line__receipt_id", flat=True))
        if not used_ids.issubset(ids):
            raise serializers.ValidationError("Un ricevimento e' ancora utilizzato nelle righe fattura.")
        invoice.receipt_links.exclude(receipt_id__in=ids).delete()
        for receipt in receipts:
            SupplierInvoiceReceipt.objects.get_or_create(invoice=invoice, receipt=receipt)
        return Response({"invoice": str(invoice.pk), "receipts": sorted(str(value) for value in ids)})
    base.set_receipts = set_receipts
    return base
