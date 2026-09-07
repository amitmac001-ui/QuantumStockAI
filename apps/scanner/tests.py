from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.scanner.services.scan_report_cache_service import InvalidScanCache, ScanReportCacheService


class ScanReportCacheFreshnessTests(TestCase):
    def test_cache_rejects_a_different_expected_session(self):
        with TemporaryDirectory() as directory:
            cache = ScanReportCacheService(Path(directory) / "reports.json")
            cache.save(
                [],
                session=date(2026, 9, 3),
                session_context={"scanner_session": date(2026, 9, 3)},
            )
            with self.assertRaisesRegex(InvalidScanCache, "Stale scan cache"):
                cache.load(expected_session=date(2026, 9, 4))


class ScannerAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="scanner-user",
            email="scanner@example.com",
            password="strong-password-123",
        )
        self.client.force_login(self.user)

    def test_symbol_route_serializes_current_scan_report_contract(self):
        payload = {
            "symbol": "ALPHA",
            "company_name": "Alpha Industries",
            "exchange": "NSE",
            "sector": "Industrials",
            "industry": "Machinery",
            "price": 100,
            "summary": {"total_score": 80, "verdict": "Strong Candidate", "confidence": 82},
            "setup": {
                "pre_breakout": True,
                "breakout": False,
                "classification": "STRONG",
                "prebreakout_score": 80,
                "breakout_probability": 75,
                "resistance": 103,
                "support": 95,
                "distance_from_breakout": 2,
                "risk_flags": [],
                "data_quality": [],
            },
            "strategies": [
                {
                    "name": "Minervini",
                    "passed": True,
                    "score": 82,
                    "weight": 10,
                    "confidence": 82,
                    "reasons": ["Trend aligned"],
                }
            ],
            "session": "2026-09-04",
        }
        with patch(
            "apps.scanner.views.ScannerService.scan",
            return_value=payload,
        ):
            response = self.client.get("/api/v1/scanner/ALPHA/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["symbol"], "ALPHA")
        self.assertEqual(body["data"]["setup"]["classification"], "STRONG")

    def test_symbol_route_fails_closed_when_validated_cache_is_unavailable(self):
        with patch("apps.scanner.views.ScannerService.scan", return_value=None):
            response = self.client.get("/api/v1/scanner/MISSING/")
        self.assertEqual(response.status_code, 404)
