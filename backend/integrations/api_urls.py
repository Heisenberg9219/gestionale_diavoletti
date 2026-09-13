from django.urls import path

from .webhooks import ShopifyWebhookView


urlpatterns = [
    path(
        "shopify/<slug:connection_code>/webhook/",
        ShopifyWebhookView.as_view(),
        name="shopify-webhook",
    ),
]
