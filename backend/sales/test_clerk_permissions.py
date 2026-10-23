from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserPagePermission
from . import tests as fixtures


class ClerkSalePermissionTests(TestCase):
    """Togliere articoli o pagamenti richiede il permesso "cancellare"."""

    @classmethod
    def setUpTestData(cls):
        fixtures.SalesServiceTests.setUpTestData.__func__(cls)
        cls.user.groups.add(Group.objects.get(name="Commesso"))

    create_sale = fixtures.SalesServiceTests.create_sale
    add_standard_line = fixtures.SalesServiceTests.add_standard_line

    def setUp(self):
        fixtures.SalesServiceTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.sale = self.create_sale()
        self.line = self.add_standard_line(sale=self.sale)

    def grant(self, **flags):
        UserPagePermission.objects.update_or_create(
            user=self.user, page_key="Nuova vendita",
            defaults={"can_view": True, "can_create": False, "can_update": False, "can_delete": False, **flags},
        )

    def post(self, action, data):
        return self.client.post(f"/api/v1/sales/sales/{self.sale.pk}/{action}/", data, format="json")

    def test_create_permission_can_add_but_not_remove(self):
        self.grant(can_create=True)
        self.assertEqual(self.post("set-line", {"variant": str(self.variant.pk), "quantity": 2}).status_code, 200)
        self.assertEqual(self.post("remove-line", {"line": str(self.line.pk), "reason": "x"}).status_code, 403)
        self.assertEqual(self.post("cancel", {"reason": "x"}).status_code, 403)

    def test_delete_permission_allows_removing_lines(self):
        self.grant(can_create=True, can_delete=True)
        self.assertEqual(self.post("remove-line", {"line": str(self.line.pk), "reason": "x"}).status_code, 200)

    def test_remove_payment_requires_delete(self):
        self.grant(can_create=True)
        response = self.post("remove-payment", {"payment": "00000000-0000-0000-0000-000000000000", "reason": "x"})
        self.assertEqual(response.status_code, 403)
