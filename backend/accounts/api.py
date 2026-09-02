from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import CurrentUserSerializer, LoginSerializer


def _set_refresh_cookie(response, refresh):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path="/api/v1/auth/",
    )


def _delete_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path="/api/v1/auth/",
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


class LoginView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request=request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None or not user.is_active or user.status != user.Status.ACTIVE:
            return Response(
                {"detail": "Email o password non valide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        refresh = RefreshToken.for_user(user)
        response = Response({
            "access": str(refresh.access_token),
            "user": CurrentUserSerializer(user).data,
        })
        _set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "Sessione non disponibile."}, status=401)
        try:
            old_refresh = RefreshToken(raw_token)
            user = get_user_model().objects.get(pk=old_refresh["user_id"])
            if not user.is_active or user.status != user.Status.ACTIVE:
                raise get_user_model().DoesNotExist
            old_refresh.blacklist()
            new_refresh = RefreshToken.for_user(user)
        except (TokenError, get_user_model().DoesNotExist, ValueError):
            response = Response({"detail": "Sessione non valida o scaduta."}, status=401)
            _delete_refresh_cookie(response)
            return response
        response = Response({"access": str(new_refresh.access_token)})
        _set_refresh_cookie(response, new_refresh)
        return response


class LogoutView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if raw_token:
            try:
                RefreshToken(raw_token).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _delete_refresh_cookie(response)
        return response


class CurrentUserView(APIView):
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
