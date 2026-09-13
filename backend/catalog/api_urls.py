from rest_framework.routers import DefaultRouter

from .api import BrandViewSet, CategoryViewSet, ColorViewSet, ProductBarcodeViewSet, ProductVariantViewSet, ProductViewSet, SeasonViewSet, SizeScaleViewSet, SizeViewSet

router = DefaultRouter()
router.register("brands", BrandViewSet)
router.register("categories", CategoryViewSet)
router.register("seasons", SeasonViewSet)
router.register("colors", ColorViewSet)
router.register("size-scales", SizeScaleViewSet)
router.register("sizes", SizeViewSet)
router.register("products", ProductViewSet)
router.register("variants", ProductVariantViewSet)
router.register("barcodes", ProductBarcodeViewSet)
urlpatterns = router.urls
