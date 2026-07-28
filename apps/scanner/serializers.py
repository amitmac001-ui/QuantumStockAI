from rest_framework import serializers

from apps.market.models import MarketQuote


class ScannerSerializer(serializers.ModelSerializer):

    class Meta:

        model = MarketQuote

        fields = (
            "symbol",
            "exchange",
            "company_name",
            "last_price",
            "change",
            "change_percent",
            "volume",
            "market_status",
            "updated_at",
        )

class ScanStrategySerializer(serializers.Serializer):

    strategy = serializers.CharField()
    signal = serializers.CharField()
    score = serializers.FloatField()
    confidence = serializers.FloatField()
    reason = serializers.CharField()


class ScanSummarySerializer(serializers.Serializer):

    total_score = serializers.FloatField()
    verdict = serializers.CharField()
    confidence = serializers.FloatField()


class ScanResultSerializer(serializers.Serializer):

    symbol = serializers.CharField()

    summary = ScanSummarySerializer()

    strategies = ScanStrategySerializer(
        many=True,
    )
