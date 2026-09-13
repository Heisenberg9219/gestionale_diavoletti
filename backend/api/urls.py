from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("auth/", include("accounts.api_urls")),
    path("core/", include("core.api_urls")),
    path("catalog/", include("catalog.api_urls")),
    path("suppliers/", include("suppliers.api_urls")),
    path("pricing/", include("pricing.api_urls")),
    path("inventory/", include("inventory.api_urls")),
    path("customers/", include("customers.api_urls")),
    path("sales/", include("sales.api_urls")),
    path("reporting/", include("reporting.api_urls")),
    path("integrations/", include("integrations.api_urls")),
    path("", include("api.domain_urls")),
]
