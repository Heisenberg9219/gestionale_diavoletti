from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APITestCase

from .models import Location


class CoreApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="core-owner@test.it", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        cls.clerk = get_user_model().objects.create_user(email="core-clerk@test.it", password="x")
        cls.clerk.groups.add(Group.objects.get(name="Commesso"))

    def test_clerk_can_read_but_cannot_create_location(self):
        self.client.force_authenticate(self.clerk)
        self.assertEqual(self.client.get("/api/v1/core/locations/").status_code, 200)
        response = self.client.post("/api/v1/core/locations/", {"code": "API_LOC", "name": "Sede API", "type": Location.Type.OTHER}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_owner_can_create_and_archive_location(self):
        self.client.force_authenticate(self.owner)
        created = self.client.post("/api/v1/core/locations/", {"code": "API_LOC", "name": "Sede API", "type": Location.Type.OTHER}, format="json")
        self.assertEqual(created.status_code, 201)
        deleted = self.client.delete(f"/api/v1/core/locations/{created.data['id']}/")
        self.assertEqual(deleted.status_code, 204)
        location = Location.objects.get(pk=created.data["id"])
        self.assertFalse(location.is_active)
        self.assertIsNotNone(location.archived_at)
