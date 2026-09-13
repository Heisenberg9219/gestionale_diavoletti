from rest_framework import serializers

from .models import Supplier, SupplierVariant


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "archived_at")


class SupplierVariantSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.business_name", read_only=True)
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)

    class Meta:
        model = SupplierVariant
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
