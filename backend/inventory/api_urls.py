from rest_framework.routers import DefaultRouter
from .api import InventoryCostViewSet, InventoryCountLineViewSet, InventoryCountSessionViewSet, StockBalanceViewSet, StockMovementViewSet

router = DefaultRouter()
router.register("stock", StockBalanceViewSet)
router.register("costs", InventoryCostViewSet)
router.register("movements", StockMovementViewSet)
router.register("counts", InventoryCountSessionViewSet)
router.register("count-lines", InventoryCountLineViewSet)
urlpatterns = router.urls
