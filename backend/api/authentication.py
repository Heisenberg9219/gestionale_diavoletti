from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class ActiveUserJWTScheme(SimpleJWTScheme):
    target_class = "api.authentication.ActiveUserJWTAuthentication"
    name = "jwtAuth"


class ActiveUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_active or user.status != user.Status.ACTIVE:
            raise AuthenticationFailed("Account non attivo.", code="user_inactive")
        return user
