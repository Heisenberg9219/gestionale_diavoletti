from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from .models import ReportDashboard, ReportWidget
from .services import ensure_reporting_access, resolve_period


class ReportingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(email="owner-report@test.it", password="x")
        cls.owner.groups.add(Group.objects.get(name="Titolare"))
        cls.clerk = get_user_model().objects.create_user(email="clerk-report@test.it", password="x")
        cls.dashboard = ReportDashboard.objects.create(code="MAIN", name="Dashboard", created_by=cls.owner, updated_by=cls.owner)

    def widget(self, period, **kwargs):
        return ReportWidget.objects.create(dashboard=self.dashboard, title="Vendite", visualization=ReportWidget.Visualization.KPI, metric=ReportWidget.Metric.REVENUE, period=period, created_by=self.owner, updated_by=self.owner, **kwargs)

    def test_only_owner_can_access_reporting(self):
        ensure_reporting_access(self.owner)
        with self.assertRaises(PermissionDenied):
            ensure_reporting_access(self.clerk)

    def test_dynamic_week_period(self):
        widget = self.widget(ReportWidget.Period.THIS_WEEK)
        self.assertEqual(resolve_period(widget, today=date(2026, 9, 2)), (date(2026, 8, 31), date(2026, 9, 2)))

    def test_custom_period(self):
        widget = self.widget(ReportWidget.Period.CUSTOM, custom_date_from=date(2025, 1, 1), custom_date_to=date(2025, 12, 31))
        self.assertEqual(resolve_period(widget), (date(2025, 1, 1), date(2025, 12, 31)))
