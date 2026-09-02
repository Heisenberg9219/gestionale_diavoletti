from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


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

    def test_existing_access_token_stops_working_when_user_is_blocked(self):
        login = self.login()
        self.owner.status = User.Status.BLOCKED
        self.owner.save(update_fields=("status", "updated_at"))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
