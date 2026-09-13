from rest_framework import serializers
from .models import ConsentPurpose, Customer, CustomerChild, CustomerConsentEvent


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    class Meta:
        model = Customer; fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "archived_at", "created_by")


class CustomerChildSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    class Meta:
        model = CustomerChild; fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "archived_at")


class ConsentPurposeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsentPurpose; fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class CustomerConsentEventSerializer(serializers.ModelSerializer):
    purpose_code = serializers.CharField(source="purpose.code", read_only=True)
    class Meta:
        model = CustomerConsentEvent; fields = "__all__"
        read_only_fields = ("id", "notice_version", "notice_text", "occurred_at", "collected_by", "created_at", "updated_at")
