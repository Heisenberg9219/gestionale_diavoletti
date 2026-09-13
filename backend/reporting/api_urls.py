from django.urls import path

from .api import OverviewAPIView


urlpatterns = [
    path("overview/", OverviewAPIView.as_view(), name="reporting-overview"),
]
