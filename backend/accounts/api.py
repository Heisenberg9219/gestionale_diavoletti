from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

from .models import UserPagePermission
from .serializers import CurrentUserSerializer, LoginSerializer, ManagedUserSerializer
from api.permissions import IsOwner
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers


def _set_refresh_cookie(response, refresh):
    seconds_until_session_expiry = int(refresh["session_expires_at"] - timezone.now().timestamp())
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(refresh),
        max_age=min(
            seconds_until_session_expiry,
            int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        ),
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


def _create_refresh_token(user, *, session_expires_at=None, idle_expires_at=None):
    refresh = RefreshToken.for_user(user)
    refresh["session_expires_at"] = session_expires_at or int(
        (timezone.now() + settings.AUTH_SESSION_MAX_LIFETIME).timestamp()
    )
    refresh["idle_expires_at"] = idle_expires_at or int(
        (timezone.now() + settings.AUTH_SESSION_IDLE_TIMEOUT).timestamp()
    )
    return refresh


class LoginView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(request=LoginSerializer, responses=inline_serializer(name="LoginResponse", fields={"access": serializers.CharField(), "user": CurrentUserSerializer()}))
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
        refresh = _create_refresh_token(user)
        response = Response({
            "access": str(refresh.access_token),
            "user": CurrentUserSerializer(user).data,
        })
        _set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    @extend_schema(request=None, responses=inline_serializer(name="RefreshResponse", fields={"access": serializers.CharField()}))
    def post(self, request):
        raw_token = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if not raw_token:
            return Response({"detail": "Sessione non disponibile."}, status=401)
        try:
            old_refresh = RefreshToken(raw_token)
            user = get_user_model().objects.get(pk=old_refresh["user_id"])
            if not user.is_active or user.status != user.Status.ACTIVE:
                raise get_user_model().DoesNotExist
            session_expires_at = old_refresh.get("session_expires_at")
            if session_expires_at is not None and timezone.now().timestamp() >= session_expires_at:
                raise TokenError("Sessione scaduta.")
            idle_expires_at = old_refresh.get("idle_expires_at")
            if idle_expires_at is not None and timezone.now().timestamp() >= idle_expires_at:
                raise TokenError("Sessione scaduta per inattività.")
            old_refresh.blacklist()
            new_refresh = _create_refresh_token(
                user,
                session_expires_at=session_expires_at,
            )
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

    @extend_schema(request=None, responses={204: None})
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
    @extend_schema(responses=CurrentUserSerializer)
    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)


class ManagedUsersView(APIView):
    permission_classes = (IsOwner,)

    def get(self, request):
        users = get_user_model().objects.exclude(status=get_user_model().Status.ARCHIVED).order_by("first_name", "last_name", "email")
        return Response(ManagedUserSerializer(users, many=True).data)

    def post(self, request):
        serializer = ManagedUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(ManagedUserSerializer(serializer.save()).data, status=status.HTTP_201_CREATED)


class ManagedUserDetailView(APIView):
    permission_classes = (IsOwner,)

    def get_object(self, pk):
        from django.shortcuts import get_object_or_404
        return get_object_or_404(get_user_model(), pk=pk)

    def patch(self, request, pk):
        user = self.get_object(pk)
        if user == request.user:
            if request.data.get("status") in {"BLOCKED", "ARCHIVED"}:
                return Response({"detail": "Non puoi bloccare il tuo stesso utente."}, status=status.HTTP_400_BAD_REQUEST)
            if "role_names" in request.data and "Titolare" not in request.data["role_names"]:
                return Response({"detail": "Non puoi rimuovere il tuo ruolo Titolare."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ManagedUserSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(ManagedUserSerializer(serializer.save()).data)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if user == request.user:
            return Response({"detail": "Non puoi eliminare il tuo stesso utente."}, status=status.HTTP_400_BAD_REQUEST)
        user.status = user.Status.ARCHIVED
        user.is_active = False
        user.save(update_fields=("status", "is_active", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolesView(APIView):
    permission_classes = (IsOwner,)

    def get(self, request):
        for name in ("Titolare", "Commesso"):
            Group.objects.get_or_create(name=name)
        groups = Group.objects.filter(name__in=("Titolare", "Commesso")).order_by("name")
        return Response([{"name": group.name, "description": getattr(getattr(group, "role_metadata", None), "description", ""), "is_active": getattr(getattr(group, "role_metadata", None), "is_active", True)} for group in groups])


PAGE_PERMISSIONS = (
    ("Storico vendite", "Storico vendite"), ("Nuova vendita", "Nuova vendita"),
    ("Cassa", "Cassa"), ("Resi", "Resi"),
    ("Catalogo", "Catalogo"), ("Magazzino", "Magazzino"),
    ("Inventari", "Inventari"), ("Riordini", "Riordini"),
    ("Clienti", "Clienti"), ("Fedeltà", "Fedeltà"), ("Buoni", "Buoni"),
    ("Liste regalo", "Liste regalo"), ("Fornitori", "Fornitori"),
    ("Ordini acquisto", "Ordini acquisto"), ("Promozioni", "Promozioni"),
    ("Spese", "Spese"), ("Documenti e OCR", "Documenti e OCR"),
    ("Notifiche", "Notifiche"),
)


class UserPagePermissionsView(APIView):
    permission_classes = (IsOwner,)

    def get_user(self, pk):
        from django.shortcuts import get_object_or_404
        user = get_object_or_404(get_user_model(), pk=pk)
        if not user.groups.filter(name="Commesso").exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("I permessi personalizzati sono disponibili solo per il ruolo Commesso.")
        return user

    def rows(self, user):
        existing = {item.page_key: item for item in user.page_permissions.all()}
        rows = []
        for key, label in PAGE_PERMISSIONS:
            permission, _ = UserPagePermission.objects.get_or_create(
                user=user, page_key=key, defaults={"can_view": False}
            )
            rows.append({
                "page_key": key, "label": label, "can_view": permission.can_view,
                "can_create": permission.can_create, "can_update": permission.can_update,
                "can_delete": permission.can_delete,
            })
        return rows

    def get(self, request, pk):
        return Response(self.rows(self.get_user(pk)))

    def patch(self, request, pk):
        user = self.get_user(pk)
        values = request.data.get("permissions")
        if not isinstance(values, list):
            return Response({"detail": "Permessi non validi."}, status=status.HTTP_400_BAD_REQUEST)
        allowed = {key for key, _ in PAGE_PERMISSIONS}
        for value in values:
            key = value.get("page_key")
            if key not in allowed:
                return Response({"detail": "Pagina non valida."}, status=status.HTTP_400_BAD_REQUEST)
            can_create = bool(value.get("can_create", False))
            can_update = bool(value.get("can_update", False))
            can_delete = bool(value.get("can_delete", False))
            UserPagePermission.objects.update_or_create(
                user=user, page_key=key,
                defaults={
                    "can_view": bool(value.get("can_view", False)) or can_create or can_update or can_delete,
                    "can_create": can_create, "can_update": can_update, "can_delete": can_delete,
                },
            )
        return Response(self.rows(user))
