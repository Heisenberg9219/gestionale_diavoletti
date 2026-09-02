from django.urls import path

from .api import CurrentUserView, LoginView, LogoutView, RefreshView


urlpatterns = [
    path("login/", LoginView.as_view(), name="api-login"),
    path("refresh/", RefreshView.as_view(), name="api-refresh"),
    path("logout/", LogoutView.as_view(), name="api-logout"),
    path("me/", CurrentUserView.as_view(), name="api-current-user"),
]
