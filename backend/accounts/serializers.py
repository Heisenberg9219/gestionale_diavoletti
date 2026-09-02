from rest_framework import serializers

from .models import User


class CurrentUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "email", "first_name", "last_name", "status", "roles",
            "is_superuser",
        )

    def get_roles(self, obj):
        return list(obj.groups.order_by("name").values_list("name", flat=True))


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)
