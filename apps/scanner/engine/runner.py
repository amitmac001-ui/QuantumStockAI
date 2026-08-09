"""
Legacy Scanner Engine

Deprecated.

This module is kept only for backward compatibility.

Use:
apps.scanner.engine.decision_engine.scanner_engine
instead.
"""

from apps.scanner.engine.decision_engine import scanner_engine


class ScannerEngine:

    @classmethod
    def run(cls, snapshot):

        report = scanner_engine.scan(snapshot)

        if report is None:
            return []

        return report.results