from django.test import SimpleTestCase, TestCase

from apps.companies.models import Company
from apps.companies.services.instrument_classification import (
    InstrumentClassificationService,
)


class InstrumentClassificationTests(SimpleTestCase):
    def test_authoritative_fields_separate_equity_etf_debt_and_other(self):
        classify = InstrumentClassificationService.classify
        self.assertEqual(
            classify(segment="NSE_EQ", instrument_type="EQ", security_type="NORMAL", isin="INE002A01018"),
            Company.SecurityCategory.OPERATING_EQUITY,
        )
        self.assertEqual(
            classify(segment="NSE_EQ", instrument_type="EQ", security_type="NORMAL", isin="INF000000001"),
            Company.SecurityCategory.ETF,
        )
        self.assertEqual(
            classify(segment="NSE_EQ", instrument_type="N0", security_type="NORMAL", isin="INE000000001"),
            Company.SecurityCategory.DEBT,
        )
        self.assertEqual(
            classify(segment="NSE_FO", instrument_type="CE", security_type="NORMAL", isin=""),
            Company.SecurityCategory.OTHER,
        )


class ScannerEligibilityTests(TestCase):
    def test_only_normal_operating_company_equity_is_launch_eligible(self):
        common = {
            "exchange": "NSE", "is_active": True,
            "instrument_status": Company.InstrumentStatus.ACTIVE,
            "provider_segment": "NSE_EQ", "provider_instrument_type": "EQ",
            "upstox_instrument_key": "NSE_EQ|INE000000001",
        }
        equity = Company.objects.create(
            symbol="EQUITY", name="Equity", provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.OPERATING_EQUITY, **common,
        )
        Company.objects.create(
            symbol="ETF", name="ETF", provider_security_type="NORMAL",
            security_category=Company.SecurityCategory.ETF,
            **{**common, "upstox_instrument_key": "NSE_EQ|INF000000001"},
        )
        Company.objects.create(
            symbol="SME", name="SME", provider_security_type="SME",
            security_category=Company.SecurityCategory.OPERATING_EQUITY,
            **{**common, "upstox_instrument_key": "NSE_EQ|INE000000002"},
        )
        self.assertEqual(list(Company.scanner_eligible()), [equity])
