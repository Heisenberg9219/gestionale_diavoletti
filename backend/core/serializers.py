from rest_framework import serializers

from .models import Location, ShopSettings, TaxRate


class ShopSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopSettings
        exclude = ("singleton_key",)
        read_only_fields = ("id", "created_at", "updated_at")


class LocationSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Location
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "archived_at")


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")
