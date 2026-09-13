from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from api.domain_urls import routers
from reporting.models import ReportDashboard


class DomainApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create(email="api-owner@example.test", is_superuser=True)
        cls.clerk = get_user_model().objects.create(email="api-clerk@example.test")
        cls.clerk.groups.add(Group.objects.get_or_create(name="Commesso")[0])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_all_domain_lists_are_serializable(self):
        for domain, router in routers.items():
            for prefix, view, basename in router.registry:
                with self.subTest(domain=domain, resource=prefix):
                    response = self.client.get(f"/api/v1/{domain}/{prefix}/")
                    self.assertEqual(response.status_code, 200, response.data)

    def test_lists_require_authentication(self):
        self.client.force_authenticate(None)
        for domain, router in routers.items():
            prefix = router.registry[0][0]
            with self.subTest(domain=domain):
                self.assertEqual(self.client.get(f"/api/v1/{domain}/{prefix}/").status_code, 401)

    def test_dashboard_creation_sets_audit_users(self):
        response = self.client.post("/api/v1/reporting/dashboards/", {"code": "TEST-API", "name": "Dashboard"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        dashboard = ReportDashboard.objects.get(pk=response.data["id"])
        self.assertEqual(dashboard.created_by, self.owner)
        self.assertEqual(dashboard.updated_by, self.owner)

    def test_clerk_cannot_adjust_points_or_see_reporting(self):
        self.client.force_authenticate(self.clerk)
        self.assertEqual(self.client.post("/api/v1/loyalty/point-movements/adjust/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/reporting/widgets/").status_code, 403)

    def test_collection_commands_reject_missing_inputs(self):
        paths = ["loyalty/earning-activations/activate", "loyalty/point-movements/adjust", "loyalty/issued-rewards/issue", "vouchers/vouchers/issue", "returns/returns/create-draft", "reorders/items/add", "integrations/sync-events/enqueue-inventory"]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.post(f"/api/v1/{path}/", {}, format="json").status_code, 400)

    def test_voucher_redemption_returns_movement_and_payment(self):
        from core.models import Location
        from sales.models import Sale
        from vouchers.services import issue_voucher
        location = Location.objects.create(code="API-VOUCHER", name="Test", type="SALES_FLOOR")
        sale = Sale.objects.create(location=location, opened_by=self.owner, subtotal_amount="30.00", calculated_total_amount="30.00", final_total_amount="30.00")
        voucher = issue_voucher(voucher_type="GIFT_CARD", initial_amount="50.00", issued_by=self.owner)
        response = self.client.post(f"/api/v1/vouchers/vouchers/{voucher.pk}/redeem/", {"sale": str(sale.pk), "amount": "20.00"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("movement", response.data)
        self.assertIn("payment", response.data)

    def test_closing_contribution_list_returns_voucher(self):
        from core.models import Location
        from giftlists.models import GiftList
        from giftlists.services import add_contribution
        location = Location.objects.create(code="API-GIFTS", name="Test", type="SALES_FLOOR")
        gift_list = GiftList.objects.create(code="API-GIFT", list_type="BIRTHDAY", mode="CONTRIBUTIONS", title="Test", beneficiary_first_name="Anna", beneficiary_last_name="Rossi", location=location, created_by=self.owner)
        add_contribution(gift_list=gift_list, first_name="Mario", last_name="Rossi", amount="20.00", payment_method="CASH", recorded_by=self.owner)
        response = self.client.post(f"/api/v1/gift-lists/lists/{gift_list.pk}/close/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data["voucher"])

    def test_invalid_monetary_input_is_400(self):
        response = self.client.post("/api/v1/vouchers/vouchers/issue/", {"voucher_type": "GIFT_CARD", "initial_amount": "not-money"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_notifications_are_private_to_recipient(self):
        from notifications.models import Notification, NotificationDelivery
        notification = Notification.objects.create(notification_type="SYSTEM", title="Private", message="Private", deduplication_key="API-PRIVATE")
        delivery = NotificationDelivery.objects.create(notification=notification, user=self.owner)
        self.client.force_authenticate(self.clerk)
        self.assertEqual(self.client.get(f"/api/v1/notifications/notifications/{notification.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/notifications/deliveries/{delivery.pk}/mark-read/", {}, format="json").status_code, 404)

    def test_csv_export_is_downloadable_and_tracked(self):
        from reporting.models import ReportWidget, ReportExport
        dashboard = ReportDashboard.objects.create(code="CSV", name="CSV", created_by=self.owner, updated_by=self.owner)
        widget = ReportWidget.objects.create(dashboard=dashboard, title="Test", visualization="KPI", metric="SALES", period="TODAY", created_by=self.owner, updated_by=self.owner)
        response = self.client.post(f"/api/v1/reporting/widgets/{widget.pk}/export-csv/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertTrue(ReportExport.objects.filter(widget=widget, status="COMPLETED").exists())
