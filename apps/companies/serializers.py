from rest_framework import serializers

from .models import Company


class CompanyListSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Company

        fields = (
            "id",
            "symbol",
            "display_name",
            "name",
            "exchange",
            "sector",
            "industry",
            "market_cap",
        )

    def get_display_name(self, obj):
        return f"{obj.symbol} • {obj.name}"


class CompanyDetailSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Company

        fields = (
            "id",
            "symbol",
            "display_name",
            "name",
            "exchange",
            "isin",
            "series",
            "sector",
            "industry",
            "listing_date",
            "face_value",
            "market_cap",
            "is_active",
            "created_at",
            "updated_at",
        )

    def get_display_name(self, obj):
        return f"{obj.symbol} • {obj.name}"
