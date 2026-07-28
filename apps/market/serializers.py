from rest_framework import serializers

from .models import (
    MarketQuote,
    MarketOHLC,
)


class MarketQuoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = MarketQuote

        fields = "__all__"


class MarketOHLCSerializer(serializers.ModelSerializer):

    class Meta:
        model = MarketOHLC

        fields = "__all__"
