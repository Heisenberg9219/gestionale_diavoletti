from rest_framework.routers import DefaultRouter

from .api import LocationViewSet, ShopSettingsViewSet, TaxRateViewSet

router = DefaultRouter()
router.register("settings", ShopSettingsViewSet, basename="shop-settings")
router.register("locations", LocationViewSet)
router.register("tax-rates", TaxRateViewSet)
urlpatterns = router.urls
