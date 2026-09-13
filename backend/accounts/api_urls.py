from django.urls import path

from .api import CurrentUserView, LoginView, LogoutView, ManagedUserDetailView, ManagedUsersView, RefreshView, RolesView, UserPagePermissionsView


urlpatterns = [
    path("login/", LoginView.as_view(), name="api-login"),
    path("refresh/", RefreshView.as_view(), name="api-refresh"),
    path("logout/", LogoutView.as_view(), name="api-logout"),
    path("me/", CurrentUserView.as_view(), name="api-current-user"),
    path("users/", ManagedUsersView.as_view(), name="api-managed-users"),
    path("users/<uuid:pk>/", ManagedUserDetailView.as_view(), name="api-managed-user-detail"),
    path("users/<uuid:pk>/page-permissions/", UserPagePermissionsView.as_view(), name="api-user-page-permissions"),
    path("roles/", RolesView.as_view(), name="api-roles"),
]
