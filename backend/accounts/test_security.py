from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from api.throttling import FAILED_LOGIN_LIMIT

from .models import User


class LoginProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="lock@example.com", password="correct-password")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def post_login(self, password):
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": "lock@example.com", "password": password},
            format="json",
        )

    def test_repeated_failures_lock_the_email_temporarily(self):
        from api.throttling import register_failed_login
        for _ in range(FAILED_LOGIN_LIMIT):
            register_failed_login("LOCK@example.com")
        response = self.post_login("correct-password")
        self.assertEqual(response.status_code, 429)

    def test_successful_login_resets_failure_counter(self):
        self.assertEqual(self.post_login("wrong").status_code, 401)
        self.assertEqual(self.post_login("correct-password").status_code, 200)
        self.assertIsNone(cache.get("auth:failed-login:lock@example.com"))

    def test_login_is_rate_limited_per_ip(self):
        statuses = [self.post_login("wrong").status_code for _ in range(12)]
        self.assertIn(429, statuses)


class AdminBehindProxyTests(TestCase):
    """L'admin deve funzionare dietro nginx che termina HTTPS."""

    def test_admin_login_accepts_https_origin_forwarded_by_proxy(self):
        from django.test import Client, override_settings

        User.objects.create_superuser(email="admin@example.com", password="correct-password")
        client = Client(enforce_csrf_checks=True)
        headers = {"HTTP_HOST": "gestionale.example.it", "HTTP_X_FORWARDED_PROTO": "https"}
        with override_settings(ALLOWED_HOSTS=["gestionale.example.it"], CSRF_COOKIE_SECURE=False, SESSION_COOKIE_SECURE=False):
            client.get("/admin/login/", **headers)
            token = client.cookies["csrftoken"].value
            response = client.post(
                "/admin/login/",
                {"username": "admin@example.com", "password": "correct-password", "csrfmiddlewaretoken": token, "next": "/admin/"},
                HTTP_ORIGIN="https://gestionale.example.it",
                HTTP_REFERER="https://gestionale.example.it/admin/login/",
                **headers,
            )
        self.assertEqual(response.status_code, 302, response.content[:300])
