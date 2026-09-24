from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from django.utils import timezone


class ActiveUserJWTScheme(SimpleJWTScheme):
    target_class = "api.authentication.ActiveUserJWTAuthentication"
    name = "jwtAuth"


class ActiveUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        session_expires_at = validated_token.get("session_expires_at")
        if session_expires_at is not None and timezone.now().timestamp() >= session_expires_at:
            raise AuthenticationFailed("Sessione scaduta. Accedi di nuovo.", code="session_expired")
        user = super().get_user(validated_token)
        if not user.is_active or user.status != user.Status.ACTIVE:
            raise AuthenticationFailed("Account non attivo.", code="user_inactive")
        return user
