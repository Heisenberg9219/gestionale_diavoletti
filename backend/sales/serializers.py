from decimal import Decimal
from rest_framework import serializers
from .models import CashRegister, CashSession, Sale, SaleLine, SalePayment


class CashRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashRegister; fields = "__all__"; read_only_fields = ("id", "created_at", "updated_at")


class CashSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashSession; fields = "__all__"
        read_only_fields = ("id", "status", "opened_at", "opened_by", "closed_at", "closed_by", "expected_cash_amount", "counted_cash_amount", "cash_difference", "created_at", "updated_at")


class SaleLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleLine; fields = "__all__"; read_only_fields = tuple(field.name for field in SaleLine._meta.fields)


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment; fields = "__all__"; read_only_fields = tuple(field.name for field in SalePayment._meta.fields)


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True); payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.SerializerMethodField()
    location_name = serializers.CharField(source="location.name", read_only=True)
    cash_register_name = serializers.SerializerMethodField()

    def get_customer_name(self, sale):
        return sale.customer.full_name if sale.customer else ""

    def get_cash_register_name(self, sale):
        if sale.cash_session_id:
            return sale.cash_session.cash_register.name
        return ""

    class Meta:
        model = Sale; fields = "__all__"
        read_only_fields = ("id", "number", "status", "opened_at", "opened_by", "confirmed_at", "confirmed_by", "cancelled_at", "cancelled_by", "subtotal_amount", "discount_amount", "tax_amount", "calculated_total_amount", "manual_total_adjustment", "manual_total_override_amount", "manual_override_reason", "final_total_amount", "total_cost_amount", "manual_override_by", "created_at", "updated_at")


class OpenCashSerializer(serializers.Serializer):
    cash_register = serializers.UUIDField(); opening_cash_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default="0.00"); notes = serializers.CharField(required=False, allow_blank=True)


class CloseCashSerializer(serializers.Serializer): counted_cash_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class LineCommandSerializer(serializers.Serializer):
    variant = serializers.UUIDField(); quantity = serializers.IntegerField(min_value=1)
    manual_unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    reserved_stock_authorization = serializers.UUIDField(required=False, allow_null=True)
    gift_list_item = serializers.UUIDField(required=False, allow_null=True)


class TotalOverrideCommandSerializer(serializers.Serializer):
    final_total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    reason = serializers.CharField(allow_blank=False)


class PaymentCommandSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=[choice for choice in SalePayment.Method.choices if choice[0] in ("CASH", "CARD", "OTHER")]); amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    cash_received_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    transaction_reference = serializers.CharField(required=False, allow_blank=True)


class DraftReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, allow_blank=False)


class RemoveLineSerializer(DraftReasonSerializer):
    line = serializers.UUIDField()


class RemovePaymentSerializer(DraftReasonSerializer):
    payment = serializers.UUIDField()
