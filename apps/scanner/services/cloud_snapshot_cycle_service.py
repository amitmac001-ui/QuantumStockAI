from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db import connection
from django.db.models import Count, Max

from apps.companies.models import Company
from apps.market.models import CloudBenchmarkCandle, CloudDailyCandle, CloudQuoteSnapshot
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.prebreakout_outcome_service import PreBreakoutOutcomeService
from apps.scanner.services.scanner_service import ScannerService


@dataclass(slots=True)
class CloudSnapshotCycleResult:
    status: str
    latest_session: str | None
    active_instruments: int
    current_histories: int
    quote_rows: int
    benchmark_rows: int
    reports: int
    quality_counts: dict[str, int]
    captured: int
    already_recorded: int
    evaluated: int
    completed: int
    outcomes_total: int
    database_bytes: int | None
    ingestion: dict

    def as_mapping(self):
        return asdict(self)


class CloudSnapshotCycleService:
    MINIMUM_BENCHMARK_SESSIONS = 252

    @staticmethod
    def _database_bytes():
        if connection.vendor != "postgresql":
            return None
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_database_size(current_database())")
            return int(cursor.fetchone()[0])

    def run(self, *, history_limit: int = 500) -> CloudSnapshotCycleResult:
        ingestion = CloudEODIngestionService().run(history_limit=history_limit)
        latest = ingestion.latest_session
        current_histories = CloudDailyCandle.objects.filter(
            session_date=latest
        ).values("company_id").distinct().count()
        benchmark = CloudBenchmarkCandle.objects.aggregate(
            count=Count("id"), latest=Max("session_date")
        )
        quote_rows = CloudQuoteSnapshot.objects.count()
        benchmark_ready = bool(
            latest and benchmark["latest"] == latest
            and benchmark["count"] >= self.MINIMUM_BENCHMARK_SESSIONS
        )
        reports = ScannerService.scan_live_market() if benchmark_ready else []
        quality_counts: dict[str, int] = {}
        for report in reports:
            state = str(report.snapshot.data_quality_state or "UNKNOWN")
            quality_counts[state] = quality_counts.get(state, 0) + 1
        capture = PreBreakoutOutcomeService.capture(reports, latest) if reports else None
        evaluation = PreBreakoutOutcomeService.evaluate_pending()
        active = Company.objects.filter(
            exchange="NSE", is_active=True,
            instrument_status=Company.InstrumentStatus.ACTIVE,
        ).exclude(upstox_instrument_key="").count()
        fully_attempted = current_histories + ingestion.provider_empty + ingestion.provider_failed >= active
        if benchmark_ready and current_histories >= active:
            status = "HEALTHY"
        elif benchmark_ready and fully_attempted:
            status = "DEGRADED_PROVIDER_DATA"
        else:
            status = "SEEDING"
        return CloudSnapshotCycleResult(
            status=status,
            latest_session=latest.isoformat() if latest else None,
            active_instruments=active,
            current_histories=current_histories,
            quote_rows=quote_rows,
            benchmark_rows=int(benchmark["count"] or 0),
            reports=len(reports),
            quality_counts=quality_counts,
            captured=capture.captured if capture else 0,
            already_recorded=capture.already_recorded if capture else 0,
            evaluated=evaluation.evaluated,
            completed=evaluation.completed,
            outcomes_total=PreBreakoutSetupOutcome.objects.count(),
            database_bytes=self._database_bytes(),
            ingestion=ingestion.as_mapping(),
        )