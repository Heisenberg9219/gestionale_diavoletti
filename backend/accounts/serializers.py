from rest_framework import serializers

from django.contrib.auth.models import Group

from .models import User


# Le pagine della sezione Controlli restano sempre riservate al titolare.
CLERK_PAGE_KEYS = (
    "Storico vendite", "Nuova vendita", "Cassa", "Resi",
    "Catalogo", "Magazzino", "Inventari", "Riordini", "Clienti",
    "Fedeltà", "Buoni", "Liste regalo", "Fornitori", "Ordini acquisto",
    "Promozioni", "Spese", "Documenti e OCR", "Notifiche",
)


class CurrentUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    page_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "status", "roles", "page_permissions",
            "is_superuser",
        )

    def get_roles(self, obj):
        return list(obj.groups.order_by("name").values_list("name", flat=True))

    def get_page_permissions(self, obj):
        if obj.is_superuser or obj.groups.filter(name="Titolare").exists():
            return None
        pages = list(
            obj.page_permissions.filter(
                can_view=True,
                page_key__in=CLERK_PAGE_KEYS,
            ).values_list("page_key", flat=True)
        )
        return pages


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class ManagedUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    role_names = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    password = serializers.CharField(trim_whitespace=False, write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "status", "roles", "role_names",
            "password", "is_superuser", "is_active", "updated_at",
        )
        read_only_fields = ("id", "is_superuser", "is_active", "updated_at")

    def get_roles(self, obj):
        return list(obj.groups.order_by("name").values_list("name", flat=True))

    def validate_role_names(self, roles):
        allowed = {"Titolare", "Commesso"}
        invalid = set(roles) - allowed
        if invalid:
            raise serializers.ValidationError("Ruolo non valido.")
        return list(dict.fromkeys(roles))

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "La password è obbligatoria per creare un utente."})
        return attrs

    def create(self, validated_data):
        roles = validated_data.pop("role_names", ["Commesso"])
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        user.groups.set(Group.objects.filter(name__in=roles))
        return user

    def update(self, instance, validated_data):
        roles = validated_data.pop("role_names", None)
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        if roles is not None:
            instance.groups.set(Group.objects.filter(name__in=roles))
        return instance
