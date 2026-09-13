from rest_framework.routers import DefaultRouter
from .api import VariantSalePriceViewSet

router = DefaultRouter()
router.register("sale-prices", VariantSalePriceViewSet)
urlpatterns = router.urls
