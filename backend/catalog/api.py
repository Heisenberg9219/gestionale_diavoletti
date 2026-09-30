import csv
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from api.viewsets import OwnerWriteReadViewSet

from .models import Brand, Category, Color, Product, ProductBarcode, ProductVariant, Season, Size, SizeScale, SkuSequence
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

    @action(detail=False, methods=("post",), url_path="reserve-skus")
    def reserve_skus(self, request):
        """Preview progressive SKUs without advancing the persisted counter."""
        try:
            count = int(request.data.get("count", 1))
        except (TypeError, ValueError):
            return Response({"detail": "Il numero di SKU richiesti non è valido."}, status=400)
        if not 1 <= count <= 200:
            return Response({"detail": "Puoi generare da 1 a 200 SKU alla volta."}, status=400)
        sequence = SkuSequence.objects.filter(key="GLOBAL").first()
        last_number = sequence.last_number if sequence else 0
        excluded = {
            str(sku).strip().upper()
            for sku in request.data.get("exclude_skus", [])
            if str(sku).strip()
        }
        skus = []
        next_number = last_number
        while len(skus) < count:
            next_number += 1
            sku = f"SKU-{next_number:06d}"
            if sku not in excluded and not ProductVariant.objects.filter(sku__iexact=sku).exists():
                skus.append(sku)
        return Response({"skus": skus})

    @action(detail=False, methods=("post",), url_path="bulk-update")
    @transaction.atomic
    def bulk_update(self, request):
        ids = request.data.get("variants", [])
        changes = request.data.get("changes", {})
        if not isinstance(ids, list) or not ids or not isinstance(changes, dict):
            return Response({"detail": "Seleziona almeno una riga e una modifica."}, status=400)
        allowed_fields = {"brand", "category", "season", "color", "size", "sale_price"}
        unknown_fields = set(changes) - allowed_fields
        if unknown_fields:
            return Response({"detail": "Sono presenti campi non modificabili."}, status=400)
        if not changes:
            return Response({"detail": "Seleziona almeno un valore da modificare."}, status=400)
        if "sale_price" in changes:
            try:
                sale_price = Decimal(str(changes["sale_price"]))
            except (InvalidOperation, TypeError):
                return Response({"detail": "Il prezzo di vendita non è valido."}, status=400)
            if sale_price <= 0:
                return Response({"detail": "Il prezzo di vendita deve essere maggiore di zero."}, status=400)
        variants = list(self.get_queryset().filter(pk__in=ids).select_for_update())
        if len(variants) != len(set(map(str, ids))):
            return Response({"detail": "Una o più righe non sono disponibili."}, status=400)
        product_fields = {key: changes[key] for key in ("brand", "category", "season") if key in changes}
        variant_fields = {key: changes[key] for key in ("color", "size") if key in changes}
        related_models = {"brand": Brand, "category": Category, "season": Season, "color": Color, "size": Size}
        for field, value in {**product_fields, **variant_fields}.items():
            if not value or not related_models[field].objects.filter(pk=value).exists():
                raise ValidationError({"detail": f"Il valore selezionato per {field} non è disponibile."})
        for variant in variants:
            if variant_fields:
                candidate = ProductVariant.objects.get(pk=variant.pk)
                for key, value in variant_fields.items():
                    setattr(candidate, f"{key}_id", value)
                try:
                    candidate.full_clean()
                except DjangoValidationError as error:
                    raise ValidationError({"detail": " ".join(error.messages)}) from error
        for variant in variants:
            if product_fields:
                Product.objects.filter(pk=variant.product_id).update(**{f"{key}_id": value for key, value in product_fields.items()}, updated_at=timezone.now())
            if variant_fields:
                for key, value in variant_fields.items(): setattr(variant, f"{key}_id", value)
                variant.full_clean(); variant.save()
        if "sale_price" in changes:
            from pricing.models import VariantSalePrice
            for variant in variants:
                VariantSalePrice.objects.filter(variant=variant, valid_until__isnull=True).update(valid_until=timezone.now())
                VariantSalePrice.objects.create(variant=variant, amount=sale_price, source=VariantSalePrice.Source.MANUAL, created_by=request.user)
        return Response({"updated": len(variants)})

    @action(detail=False, methods=("post",), url_path="bulk-archive")
    @transaction.atomic
    def bulk_archive(self, request):
        ids = request.data.get("variants", [])
        variants = self.get_queryset().filter(pk__in=ids).select_for_update()
        now = timezone.now(); updated = variants.update(is_active=False, archived_at=now, updated_at=now)
        return Response({"archived": updated})

    @action(detail=False, methods=("post",), url_path="export-csv")
    def export_csv(self, request):
        variants = self.get_queryset().filter(pk__in=request.data.get("variants", []))
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="catalogo.csv"'; response.write("\ufeff")
        writer = csv.writer(response, delimiter=";"); writer.writerow(("Articolo", "Marca", "Categoria", "Collezione", "SKU", "Colore", "Taglia", "Barcode"))
        for item in variants:
            writer.writerow((item.product.name, item.product.brand.name if item.product.brand else "", item.product.category.name, item.product.season.name if item.product.season else "", item.sku, item.color.name if item.color else "", item.size.label, ", ".join(item.barcodes.values_list("code", flat=True))))
        return response


class ProductBarcodeViewSet(OwnerWriteReadViewSet):
    queryset = ProductBarcode.objects.select_related("variant"); serializer_class = ProductBarcodeSerializer
    filter_backends = (filters.SearchFilter, filters.OrderingFilter); search_fields = ("code", "variant__sku")
    ordering_fields = ("code", "created_at")
    def get_queryset(self):
        queryset = super().get_queryset()
        if variant := self.request.query_params.get("variant"): queryset = queryset.filter(variant_id=variant)
        return queryset
