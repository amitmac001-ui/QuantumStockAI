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
    name = serializers.CharField()
    passed = serializers.BooleanField()
    score = serializers.FloatField()
    weight = serializers.FloatField()
    confidence = serializers.FloatField()
    reasons = serializers.ListField(child=serializers.CharField())


class ScanSummarySerializer(serializers.Serializer):

    total_score = serializers.FloatField()
    verdict = serializers.CharField()
    confidence = serializers.FloatField()


class ScanSetupSerializer(serializers.Serializer):
    pre_breakout = serializers.BooleanField()
    breakout = serializers.BooleanField()
    classification = serializers.CharField()
    prebreakout_score = serializers.IntegerField()
    breakout_probability = serializers.FloatField()
    resistance = serializers.FloatField()
    support = serializers.FloatField()
    distance_from_breakout = serializers.FloatField()
    risk_flags = serializers.ListField(child=serializers.CharField())
    data_quality = serializers.ListField(child=serializers.CharField())


class ScanResultSerializer(serializers.Serializer):
    symbol = serializers.CharField()
    company_name = serializers.CharField(allow_blank=True)
    exchange = serializers.CharField()
    sector = serializers.CharField(allow_blank=True)
    industry = serializers.CharField(allow_blank=True)
    price = serializers.FloatField()
    summary = ScanSummarySerializer()
    setup = ScanSetupSerializer()
    strategies = ScanStrategySerializer(many=True)
    session = serializers.CharField(allow_null=True)
