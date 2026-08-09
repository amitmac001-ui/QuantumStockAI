from django.db import models
from django.utils import timezone


class ScannerPriority(models.TextChoices):
    IGNORE = "IGNORE", "Ignore"
    WATCHLIST = "WATCHLIST", "Watchlist"
    STRONG = "STRONG", "Strong Candidate"
    ELITE = "ELITE", "Elite Setup"


class ScannerAlertStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"
    CLOSED = "CLOSED", "Closed"


class ScannerAlert(models.Model):
    symbol = models.CharField(max_length=30, db_index=True)
    company_name = models.CharField(max_length=255, blank=True, default="")
    exchange = models.CharField(max_length=10, blank=True, default="NSE", db_index=True)

    strategy_name = models.CharField(max_length=100, db_index=True)
    overall_score = models.PositiveSmallIntegerField(default=0, db_index=True)
    passed_strategies = models.PositiveSmallIntegerField(default=0)

    priority = models.CharField(
        max_length=20,
        choices=ScannerPriority.choices,
        default=ScannerPriority.IGNORE,
        db_index=True,
    )

    status = models.CharField(
        max_length=20,
        choices=ScannerAlertStatus.choices,
        default=ScannerAlertStatus.PENDING,
        db_index=True,
    )

    last_price = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    entry_low = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    entry_high = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    stop_loss = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    target_1 = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    target_2 = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    target_3 = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)

    risk_reward = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    confidence = models.PositiveSmallIntegerField(default=0)
    reason = models.TextField(blank=True, default="")

    telegram_sent = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    push_sent = models.BooleanField(default=False)

    alert_hash = models.CharField(max_length=128, unique=True, db_index=True)
    alert_time = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-alert_time", "-overall_score"]
        indexes = [
            models.Index(fields=["symbol"]),
            models.Index(fields=["strategy_name"]),
            models.Index(fields=["overall_score"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["status"]),
            models.Index(fields=["telegram_sent"]),
            models.Index(fields=["email_sent"]),
            models.Index(fields=["alert_time"]),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.strategy_name} ({self.overall_score})"


class PreBreakoutSetupOutcome(models.Model):
    """Immutable setup observation with nullable, forward-only outcome labels."""

    symbol = models.CharField(max_length=30, db_index=True)
    exchange = models.CharField(max_length=10, default="NSE", db_index=True)
    evaluation_session = models.DateField(db_index=True)
    evaluation_price = models.DecimalField(max_digits=20, decimal_places=4)
    pivot = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    raw_score = models.PositiveSmallIntegerField()
    final_score = models.PositiveSmallIntegerField()
    classification = models.CharField(max_length=20, db_index=True)
    data_quality_state = models.CharField(max_length=10, db_index=True)
    feature_snapshot = models.JSONField(default=dict)
    breakout_occurred = models.BooleanField(null=True, blank=True)
    breakout_session = models.DateField(null=True, blank=True)
    sessions_to_breakout = models.PositiveSmallIntegerField(null=True, blank=True)
    return_1d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    return_3d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    return_5d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    return_10d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    return_20d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    maximum_favorable_excursion = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    maximum_adverse_excursion = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    failed_breakout = models.BooleanField(null=True, blank=True)
    evaluated_through_session = models.DateField(null=True, blank=True)
    is_complete = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-evaluation_session", "symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange", "evaluation_session"],
                name="uq_prebreakout_setup_session",
            )
        ]
        indexes = [
            models.Index(fields=["evaluation_session", "classification"]),
            models.Index(fields=["is_complete", "evaluation_session"]),
        ]