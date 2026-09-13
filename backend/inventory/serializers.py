from rest_framework import serializers
from .models import InventoryCountLine, InventoryCountSession, StockBalance, StockMovement, VariantInventoryCost


class ReadOnlyModelSerializer(serializers.ModelSerializer):
    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            field.read_only = True
        return fields


class StockBalanceSerializer(ReadOnlyModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    class Meta:
        model = StockBalance; fields = "__all__"


class VariantInventoryCostSerializer(ReadOnlyModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    class Meta:
        model = VariantInventoryCost; fields = "__all__"


class StockMovementSerializer(ReadOnlyModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    movement_type_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    class Meta:
        model = StockMovement; fields = "__all__"


class InventoryCountSessionSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source="location.name", read_only=True)
    line_count = serializers.IntegerField(source="lines.count", read_only=True)
    class Meta:
        model = InventoryCountSession; fields = "__all__"
        read_only_fields = ("id", "status", "started_at", "confirmed_at", "cancelled_at", "created_by", "confirmed_by", "cancelled_by", "created_at", "updated_at")


class InventoryCountLineSerializer(ReadOnlyModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    class Meta:
        model = InventoryCountLine; fields = "__all__"


class CountQuantitySerializer(serializers.Serializer):
    counted_quantity = serializers.IntegerField(min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)


class TransferSerializer(serializers.Serializer):
    destination_location = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference_number = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class AdjustmentSerializer(serializers.Serializer):
    variant = serializers.UUIDField()
    location = serializers.UUIDField()
    quantity_delta = serializers.IntegerField()
    reason = serializers.CharField()

    def validate_quantity_delta(self, value):
        if value == 0: raise serializers.ValidationError("La quantità non può essere zero.")
        return value
