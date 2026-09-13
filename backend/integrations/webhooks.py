import base64
import hashlib
import hmac
import json
import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import IntegrationConnection
from .services import import_paid_shopify_order, register_webhook


class ShopifyWebhookView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request, connection_code):
        connection = get_object_or_404(
            IntegrationConnection,
            code=connection_code,
            provider=IntegrationConnection.Provider.SHOPIFY,
            is_active=True,
        )
        secret = os.environ.get(
            f"{connection.credentials_env_prefix}_WEBHOOK_SECRET",
            "",
        ).encode("utf-8")
        signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
        expected = base64.b64encode(
            hmac.new(secret, request.body, hashlib.sha256).digest()
        ).decode("utf-8")
        if not secret or not hmac.compare_digest(signature, expected):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response({"detail": "Payload Shopify non valido."}, status=400)

        event, created = register_webhook(
            connection=connection,
            external_event_id=request.headers.get("X-Shopify-Webhook-Id", ""),
            topic=request.headers.get("X-Shopify-Topic", ""),
            payload=payload,
        )
        if created and event.topic == "orders/paid":
            order = import_paid_shopify_order(connection=connection, payload=payload)
            event.status = "PROCESSED" if order.status == "IMPORTED" else "FAILED"
            event.error = order.error
            event.processed_at = order.updated_at
            event.save(update_fields=("status", "error", "processed_at", "updated_at"))
        return Response(status=status.HTTP_200_OK)
