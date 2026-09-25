from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.tokens import RefreshToken

from api.permissions import IsOwnerOrClerk

from .models import User, UserPagePermission
from .serializers import CurrentUserSerializer


class AuthenticationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            email="owner-api@example.com",
            password="correct-password",
            first_name="Mario",
        )
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        cls.blocked = User.objects.create_user(
            email="blocked-api@example.com",
            password="correct-password",
            status=User.Status.BLOCKED,
        )

    def setUp(self):
        self.client = APIClient()

    def login(self):
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": self.owner.email, "password": "correct-password"},
            format="json",
        )

    def test_login_returns_access_user_and_http_only_refresh_cookie(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["roles"], ["Titolare"])
        self.assertTrue(response.cookies["diavoletti_refresh"]["httponly"])

    def test_invalid_or_blocked_login_is_rejected(self):
        invalid = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.owner.email, "password": "wrong"},
            format="json",
        )
        blocked = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.blocked.email, "password": "correct-password"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(blocked.status_code, 401)

    def test_current_user_requires_access_token(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        login = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.owner.email)

    def test_refresh_rotates_cookie_and_logout_blacklists_it(self):
        self.login()
        old_cookie = self.client.cookies["diavoletti_refresh"].value
        refreshed = self.client.post("/api/v1/auth/refresh/")
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)
        self.assertNotEqual(
            self.client.cookies["diavoletti_refresh"].value,
            old_cookie,
        )
        logged_out = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(logged_out.status_code, 204)

    def test_refresh_keeps_the_original_absolute_session_expiry(self):
        self.login()
        old_refresh = RefreshToken(self.client.cookies["diavoletti_refresh"].value)
        original_expiry = old_refresh["session_expires_at"]

        refreshed = self.client.post("/api/v1/auth/refresh/")

        self.assertEqual(refreshed.status_code, 200)
        new_refresh = RefreshToken(self.client.cookies["diavoletti_refresh"].value)
        self.assertEqual(new_refresh["session_expires_at"], original_expiry)

    def test_refresh_rejects_an_expired_absolute_session(self):
        expired_refresh = RefreshToken.for_user(self.owner)
        expired_refresh["session_expires_at"] = int(timezone.now().timestamp()) - 1
        self.client.cookies["diavoletti_refresh"] = str(expired_refresh)

        response = self.client.post("/api/v1/auth/refresh/")

        self.assertEqual(response.status_code, 401)

    def test_refresh_rejects_an_idle_session(self):
        expired_refresh = RefreshToken.for_user(self.owner)
        expired_refresh["idle_expires_at"] = int(timezone.now().timestamp()) - 1
        self.client.cookies["diavoletti_refresh"] = str(expired_refresh)

        response = self.client.post("/api/v1/auth/refresh/")

        self.assertEqual(response.status_code, 401)

    def test_access_token_rejects_an_idle_session(self):
        refresh = RefreshToken.for_user(self.owner)
        refresh["idle_expires_at"] = int(timezone.now().timestamp()) - 1
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, 401)

    def test_existing_access_token_stops_working_when_user_is_blocked(self):
        login = self.login()
        self.owner.status = User.Status.BLOCKED
        self.owner.save(update_fields=("status", "updated_at"))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_managed_user_creation_requires_password(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/auth/users/",
            {"email": "commesso@example.com", "first_name": "Anna", "last_name": "Rossi"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["error"]["details"])

    def test_commesso_permissions_allow_the_selected_action_only(self):
        clerk = User.objects.create_user(
            email="clerk-permissions@example.com",
            password="correct-password",
        )
        clerk.groups.add(Group.objects.get(name="Commesso"))
        factory = APIRequestFactory()
        request = factory.post("/api/v1/customers/customers/", {}, format="json")
        request.user = clerk

        self.assertFalse(IsOwnerOrClerk().has_permission(request, None))
        UserPagePermission.objects.create(
            user=clerk,
            page_key="Clienti",
            can_view=True,
            can_create=True,
        )
        self.assertTrue(IsOwnerOrClerk().has_permission(request, None))

    def test_confirmation_requires_update_permission_not_create(self):
        clerk = User.objects.create_user(
            email="clerk-confirm@example.com",
            password="correct-password",
        )
        clerk.groups.add(Group.objects.get(name="Commesso"))
        UserPagePermission.objects.create(
            user=clerk,
            page_key="Resi",
            can_view=True,
            can_create=True,
        )
        request = APIRequestFactory().post("/api/v1/returns/returns/123/confirm/", {}, format="json")
        request.user = clerk

        self.assertFalse(IsOwnerOrClerk().has_permission(request, None))
        clerk.page_permissions.filter(page_key="Resi").update(can_update=True)
        self.assertTrue(IsOwnerOrClerk().has_permission(request, None))

    def test_control_pages_are_never_exposed_to_a_commesso(self):
        clerk = User.objects.create_user(
            email="clerk-controls@example.com",
            password="correct-password",
        )
        clerk.groups.add(Group.objects.get(name="Commesso"))
        UserPagePermission.objects.create(
            user=clerk,
            page_key="Report",
            can_view=True,
        )
        UserPagePermission.objects.create(
            user=clerk,
            page_key="Integrazioni",
            can_view=True,
        )
        factory = APIRequestFactory()
        report_request = factory.get("/api/v1/reporting/widgets/")
        integration_request = factory.get("/api/v1/integrations/connections/")
        report_request.user = clerk
        integration_request.user = clerk

        pages = CurrentUserSerializer(clerk).data["page_permissions"]
        self.assertNotIn("Report", pages)
        self.assertNotIn("Integrazioni", pages)
        self.assertFalse(IsOwnerOrClerk().has_permission(report_request, None))
        self.assertFalse(IsOwnerOrClerk().has_permission(integration_request, None))
