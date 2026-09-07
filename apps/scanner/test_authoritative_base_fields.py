import pandas as pd
from django.test import SimpleTestCase

from apps.scanner.engine.base_quality_features import BaseQualityFeatureExtractor
from apps.scanner.engine.decision_engine import StockSnapshot


class AuthoritativeBaseFieldTests(SimpleTestCase):
    def test_base_bounds_and_duration_come_from_pivot_qualified_ohlc(self):
        frame = pd.DataFrame(
            [
                {"high": 90, "low": 80, "close": 85},
                {"high": 104, "low": 95, "close": 101},
                {"high": 108, "low": 98, "close": 106},
                {"high": 103, "low": 96, "close": 102},
            ]
        )

        result = BaseQualityFeatureExtractor.extract(
            frame,
            pivot={"breakout_level": 100},
            structure={},
            vcp={},
        )

        self.assertEqual(result.base_duration_sessions, 3)
        self.assertEqual(result.base_high, 104.0)
        self.assertEqual(result.base_low, 80.0)
        self.assertEqual(result.base_depth_pct, 20.0)

    def test_snapshot_mapping_preserves_authoritative_base_fields(self):
        snapshot = StockSnapshot.from_mapping(
            {
                "symbol": "ALPHA",
                "base_duration_sessions": 21,
                "base_high": 112.25,
                "base_low": 99.5,
            }
        )

        self.assertEqual(snapshot.base_duration_sessions, 21)
        self.assertEqual(snapshot.base_high, 112.25)
        self.assertEqual(snapshot.base_low, 99.5)
