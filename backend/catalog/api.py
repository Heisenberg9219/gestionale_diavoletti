from rest_framework import filters

from api.viewsets import OwnerWriteReadViewSet

from .models import Brand, Category, Color, Product, ProductBarcode, ProductVariant, Season, Size, SizeScale
from .serializers import BrandSerializer, CategorySerializer, ColorSerializer, ProductBarcodeSerializer, ProductSerializer, ProductVariantSerializer, SeasonSerializer, SizeScaleSerializer, SizeSerializer


class CatalogViewSet(OwnerWriteReadViewSet):
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    ordering_fields = ("code", "name", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get("active") == "true" and hasattr(queryset.model, "is_active"):
            queryset = queryset.filter(is_active=True)
        return queryset


class BrandViewSet(CatalogViewSet):
    queryset = Brand.objects.all(); serializer_class = BrandSerializer; search_fields = ("code", "name", "description")


class CategoryViewSet(CatalogViewSet):
    queryset = Category.objects.select_related("parent"); serializer_class = CategorySerializer; search_fields = ("code", "name", "description")


class SeasonViewSet(CatalogViewSet):
    queryset = Season.objects.all(); serializer_class = SeasonSerializer; search_fields = ("code", "name")
    def get_queryset(self):
        queryset = super().get_queryset()
        if year := self.request.query_params.get("year"): queryset = queryset.filter(year=year)
        return queryset


class ColorViewSet(CatalogViewSet):
    queryset = Color.objects.all(); serializer_class = ColorSerializer; search_fields = ("code", "name", "color_family")


class SizeScaleViewSet(CatalogViewSet):
    queryset = SizeScale.objects.all(); serializer_class = SizeScaleSerializer; search_fields = ("code", "name")


class SizeViewSet(CatalogViewSet):
    queryset = Size.objects.select_related("size_scale"); serializer_class = SizeSerializer; search_fields = ("code", "label", "size_scale__name")
    def get_queryset(self):
        queryset = super().get_queryset()
        if scale := self.request.query_params.get("size_scale"): queryset = queryset.filter(size_scale_id=scale)
        return queryset


class ProductViewSet(CatalogViewSet):
    queryset = Product.objects.select_related("brand", "category", "season", "tax_rate"); serializer_class = ProductSerializer
    search_fields = ("code", "name", "description", "brand__name", "category__name")
    def get_queryset(self):
        queryset = super().get_queryset()
        for parameter, field in (("brand", "brand_id"), ("category", "category_id"), ("season", "season_id")):
            if value := self.request.query_params.get(parameter): queryset = queryset.filter(**{field: value})
        return queryset


class ProductVariantViewSet(CatalogViewSet):
    queryset = ProductVariant.objects.select_related("product", "color", "size", "size__size_scale").prefetch_related("barcodes")
    serializer_class = ProductVariantSerializer
    search_fields = ("sku", "product__code", "product__name", "barcodes__code")
    def get_queryset(self):
        queryset = super().get_queryset()
        if product := self.request.query_params.get("product"): queryset = queryset.filter(product_id=product)
        if barcode := self.request.query_params.get("barcode"): queryset = queryset.filter(barcodes__code=barcode, barcodes__is_active=True)
        return queryset.distinct()


class ProductBarcodeViewSet(OwnerWriteReadViewSet):
    queryset = ProductBarcode.objects.select_related("variant"); serializer_class = ProductBarcodeSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter); search_fields = ("code", "variant__sku")
    ordering_fields = ("code", "created_at")
    def get_queryset(self):
        queryset = super().get_queryset()
        if variant := self.request.query_params.get("variant"): queryset = queryset.filter(variant_id=variant)
        return queryset
