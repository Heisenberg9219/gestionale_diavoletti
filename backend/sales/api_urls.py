from rest_framework.routers import DefaultRouter
from .api import CashRegisterViewSet, CashSessionViewSet, SaleLineViewSet, SalePaymentViewSet, SaleViewSet

router = DefaultRouter()
router.register("registers", CashRegisterViewSet)
router.register("sessions", CashSessionViewSet)
router.register("sales", SaleViewSet)
router.register("lines", SaleLineViewSet)
router.register("payments", SalePaymentViewSet)
urlpatterns = router.urls
