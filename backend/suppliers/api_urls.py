from rest_framework.routers import DefaultRouter
from .api import SupplierVariantViewSet, SupplierViewSet

router = DefaultRouter()
router.register("suppliers", SupplierViewSet)
router.register("variant-links", SupplierVariantViewSet)
urlpatterns = router.urls
