from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db import OperationalError, close_old_connections, connection
from django.db.models import Count, Max

from apps.companies.models import Company
from apps.market.models import CloudBenchmarkCandle, CloudDailyCandle, CloudQuoteSnapshot
from apps.market.services.cloud_eod_ingestion_service import CloudEODIngestionService
from apps.scanner.models import PreBreakoutSetupOutcome
from apps.scanner.services.prebreakout_outcome_service import PreBreakoutOutcomeService
from apps.scanner.services.scan_report_cache_service import ScanReportCacheService
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
    def _database_phase(callback):
        """Run an idempotent DB phase with one forced reconnect retry."""
        close_old_connections()
        try:
            return callback()
        except OperationalError:
            connection.close()
            close_old_connections()
            return callback()

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

        def load_alignment_state():
            return (
                CloudDailyCandle.objects.filter(session_date=latest)
                .values("company_id").distinct().count(),
                CloudBenchmarkCandle.objects.aggregate(
                    count=Count("id"), latest=Max("session_date")
                ),
                CloudQuoteSnapshot.objects.count(),
            )

        current_histories, benchmark, quote_rows = self._database_phase(
            load_alignment_state
        )
        benchmark_ready = bool(
            latest and benchmark["latest"] == latest
            and benchmark["count"] >= self.MINIMUM_BENCHMARK_SESSIONS
        )
        reports = (
            self._database_phase(ScannerService.scan_live_market)
            if benchmark_ready else []
        )
        current_reports = [
            report for report in reports
            if report.snapshot.latest_daily_session is not None
            and ScanReportCacheService._session(
                report.snapshot.latest_daily_session
            ) == latest
        ]
        if current_reports:
            self._database_phase(
                lambda: ScanReportCacheService().save(
                    current_reports,
                    session=latest,
                    session_context={
                        "scanner_session": latest.isoformat(),
                        "reports": len(current_reports),
                        "source": "cloud_snapshot_cycle",
                    },
                )
            )
        quality_counts: dict[str, int] = {}
        for report in reports:
            state = str(report.snapshot.data_quality_state or "UNKNOWN")
            quality_counts[state] = quality_counts.get(state, 0) + 1
        capture = (
            self._database_phase(
                lambda: PreBreakoutOutcomeService.capture(reports, latest)
            )
            if reports else None
        )
        evaluation = self._database_phase(
            PreBreakoutOutcomeService.evaluate_pending
        )
        active = self._database_phase(lambda: Company.scanner_eligible().count())
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
            outcomes_total=self._database_phase(
                PreBreakoutSetupOutcome.objects.count
            ),
            database_bytes=self._database_phase(self._database_bytes),
            ingestion=ingestion.as_mapping(),
        )
