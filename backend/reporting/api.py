from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsOwner
from customers.models import Customer
from inventory.models import StockBalance
from sales.models import Sale, SaleLine


class OverviewAPIView(APIView):
    """Owner-only, lightweight payload for the operational landing page."""

    permission_classes = (IsOwner,)

    def get(self, request):
        today = timezone.localdate()
        sales = (
            Sale.objects.filter(
                status=Sale.Status.CONFIRMED,
                confirmed_at__date=today,
            )
            .select_related("customer")
            .order_by("-confirmed_at")
        )
        revenue = sales.aggregate(value=Sum("final_total_amount"))["value"] or Decimal("0.00")
        units = SaleLine.objects.filter(sale__in=sales).aggregate(value=Sum("quantity"))["value"] or 0

        recent_sales = []
        for sale in sales[:5]:
            customer_name = sale.customer.full_name if sale.customer else "Vendita banco"
            recent_sales.append(
                {
                    "id": str(sale.pk),
                    "number": sale.number or "Senza numero",
                    "customer_name": customer_name,
                    "confirmed_at": sale.confirmed_at.isoformat(),
                    "total_amount": str(sale.final_total_amount),
                }
            )

        return Response(
            {
                "date": today.isoformat(),
                "metrics": {
                    "revenue": str(revenue),
                    "sales_count": sales.count(),
                    "units_sold": units,
                    "new_customers": Customer.objects.filter(created_at__date=today).count(),
                },
                "recent_sales": recent_sales,
                "stock": {
                    "out_of_stock_balances": StockBalance.objects.filter(quantity_on_hand=0).count(),
                    "units_on_hand": StockBalance.objects.aggregate(value=Sum("quantity_on_hand"))["value"] or 0,
                },
            }
        )
