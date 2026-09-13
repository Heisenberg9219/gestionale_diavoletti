from rest_framework.routers import DefaultRouter
from .api import ConsentPurposeViewSet, CustomerChildViewSet, CustomerConsentEventViewSet, CustomerViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet)
router.register("children", CustomerChildViewSet)
router.register("consent-purposes", ConsentPurposeViewSet)
router.register("consent-events", CustomerConsentEventViewSet)
urlpatterns = router.urls
