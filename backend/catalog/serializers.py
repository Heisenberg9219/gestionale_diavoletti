from rest_framework import serializers

from .models import Brand, Category, Color, Product, ProductBarcode, ProductVariant, Season, Size, SizeScale


class ArchiveModelSerializer(serializers.ModelSerializer):
    class Meta:
        read_only_fields = ("id", "created_at", "updated_at", "archived_at")


class BrandSerializer(ArchiveModelSerializer):
    class Meta(ArchiveModelSerializer.Meta):
        model = Brand
        fields = "__all__"


class CategorySerializer(ArchiveModelSerializer):
    parent_name = serializers.CharField(source="parent.name", read_only=True)

    class Meta(ArchiveModelSerializer.Meta):
        model = Category
        fields = "__all__"

    def validate_parent(self, value):
        if self.instance and value and value.pk == self.instance.pk:
            raise serializers.ValidationError("Una categoria non può essere padre di se stessa.")
        return value


class SeasonSerializer(ArchiveModelSerializer):
    season_type_label = serializers.CharField(source="get_season_type_display", read_only=True)

    class Meta(ArchiveModelSerializer.Meta):
        model = Season
        fields = "__all__"


class ColorSerializer(ArchiveModelSerializer):
    class Meta(ArchiveModelSerializer.Meta):
        model = Color
        fields = "__all__"


class SizeScaleSerializer(ArchiveModelSerializer):
    scale_type_label = serializers.CharField(source="get_scale_type_display", read_only=True)

    class Meta(ArchiveModelSerializer.Meta):
        model = SizeScale
        fields = "__all__"


class SizeSerializer(ArchiveModelSerializer):
    size_scale_name = serializers.CharField(source="size_scale.name", read_only=True)

    class Meta(ArchiveModelSerializer.Meta):
        model = Size
        fields = "__all__"


class ProductSerializer(ArchiveModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    season_name = serializers.CharField(source="season.name", read_only=True)
    tax_rate_percentage = serializers.DecimalField(source="tax_rate.percentage", max_digits=5, decimal_places=2, read_only=True)

    class Meta(ArchiveModelSerializer.Meta):
        model = Product
        fields = "__all__"


class ProductVariantSerializer(ArchiveModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    color_name = serializers.CharField(source="color.name", read_only=True)
    size_label = serializers.CharField(source="size.label", read_only=True)
    barcodes = serializers.SlugRelatedField(many=True, read_only=True, slug_field="code")

    class Meta(ArchiveModelSerializer.Meta):
        model = ProductVariant
        fields = "__all__"


class ProductBarcodeSerializer(serializers.ModelSerializer):
    variant_sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = ProductBarcode
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
