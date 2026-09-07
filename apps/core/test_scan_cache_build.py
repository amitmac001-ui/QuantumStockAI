from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.scanner.services.scan_report_cache_service import ScanReportCacheService


class ScanCacheBuildCommandTests(SimpleTestCase):
    def test_zero_real_engine_matches_still_produce_valid_session_cache(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "reports.json"
            with override_settings(SCAN_REPORT_CACHE_PATH=str(path)), patch(
                "apps.core.management.commands.build_technical_scan_cache."
                "ScannerDataReadinessService.collect",
            ), patch(
                "apps.core.management.commands.build_technical_scan_cache."
                "ScannerDataReadinessService.failures",
                return_value=[],
            ), patch(
                "apps.core.management.commands.build_technical_scan_cache."
                "ScanReportCacheService.latest_aligned_session",
                return_value=date(2026, 9, 4),
            ), patch(
                "apps.core.management.commands.build_technical_scan_cache."
                "ScannerService.scan_live_market",
                return_value=[],
            ):
                call_command("build_technical_scan_cache", verbosity=0)
                reports, context = ScanReportCacheService(path).load(
                    expected_session=date(2026, 9, 4)
                )
        self.assertEqual(reports, [])
        self.assertEqual(context["scanner_session"], "2026-09-04")
