from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class ActiveUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_active or user.status != user.Status.ACTIVE:
            raise AuthenticationFailed("Account non attivo.", code="user_inactive")
        return user
