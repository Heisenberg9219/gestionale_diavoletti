from rest_framework import serializers
from .models import VariantSalePrice


class VariantSalePriceSerializer(serializers.ModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)

    class Meta:
        model = VariantSalePrice
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "created_by")
