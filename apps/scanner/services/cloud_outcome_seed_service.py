from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count

from apps.companies.models import Company
from apps.scanner.models import PreBreakoutSetupOutcome


SCHEMA_VERSION = 1
OUTCOME_FIELDS = tuple(
    field.name
    for field in PreBreakoutSetupOutcome._meta.concrete_fields
    if field.name not in {"id", "created_at", "updated_at"}
)
IMMUTABLE_OUTCOME_FIELDS = frozenset({
    "symbol", "exchange", "evaluation_session", "evaluation_price", "pivot",
    "raw_score", "final_score", "classification", "data_quality_state",
    "feature_snapshot",
})
COMPANY_FIELDS = (
    "symbol", "exchange", "name", "upstox_instrument_key", "is_active",
    "instrument_status", "instrument_status_reason",
)


class CloudOutcomeSeedError(ValueError):
    pass


class CloudOutcomeSeedService:
    """Portable, checksum-protected seed for outcome rows only.

    It intentionally excludes quotes, historical candles and unrelated local DB
    tables. Existing signal-time fields are immutable during import; only future
    outcome labels may advance.
    """

    @staticmethod
    def _digest(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _comparable(value) -> str:
        return json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True)

    @classmethod
    def export_to(cls, output: Path) -> dict[str, int]:
        output = Path(output)
        if output.exists():
            raise CloudOutcomeSeedError(f"Refusing to overwrite existing file: {output.name}")
        outcomes = list(PreBreakoutSetupOutcome.objects.values(*OUTCOME_FIELDS))
        symbols = {row["symbol"] for row in outcomes}
        companies = list(
            Company.objects.filter(symbol__in=symbols).values(*COMPANY_FIELDS)
        )
        document = {
            "schema_version": SCHEMA_VERSION,
            "companies": companies,
            "outcomes": outcomes,
        }
        payload = json.dumps(
            document, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(output)
        output.with_suffix(output.suffix + ".sha256").write_text(
            cls._digest(payload), encoding="ascii"
        )
        return {"companies": len(companies), "outcomes": len(outcomes)}

    @classmethod
    @transaction.atomic
    def import_from(cls, source: Path) -> dict[str, int]:
        source = Path(source)
        payload = source.read_bytes()
        checksum_path = source.with_suffix(source.suffix + ".sha256")
        if not checksum_path.exists():
            raise CloudOutcomeSeedError("Seed checksum file is missing.")
        expected = checksum_path.read_text(encoding="ascii").strip().lower()
        if not expected or cls._digest(payload) != expected:
            raise CloudOutcomeSeedError("Seed checksum verification failed.")
        document = json.loads(payload)
        if document.get("schema_version") != SCHEMA_VERSION:
            raise CloudOutcomeSeedError("Unsupported seed schema version.")

        companies_created = outcomes_created = outcomes_updated = 0
        for row in document.get("companies", []):
            defaults = {field: row.get(field) for field in COMPANY_FIELDS if field != "symbol"}
            company, created = Company.objects.get_or_create(
                symbol=str(row["symbol"]).upper(), defaults=defaults
            )
            companies_created += int(created)
            if not created:
                incoming_key = str(row.get("upstox_instrument_key") or "").strip()
                current_key = str(company.upstox_instrument_key or "").strip()
                if current_key and incoming_key and current_key != incoming_key:
                    raise CloudOutcomeSeedError(
                        f"Instrument-key mismatch for {company.symbol}."
                    )
                if not current_key and incoming_key:
                    company.upstox_instrument_key = incoming_key
                    company.save(update_fields=["upstox_instrument_key", "updated_at"])

        key_fields = ("symbol", "exchange", "evaluation_session")
        for row in document.get("outcomes", []):
            lookup = {field: row[field] for field in key_fields}
            defaults = {field: row.get(field) for field in OUTCOME_FIELDS if field not in key_fields}
            outcome, created = PreBreakoutSetupOutcome.objects.get_or_create(
                **lookup, defaults=defaults
            )
            if created:
                outcomes_created += 1
                continue
            for field in IMMUTABLE_OUTCOME_FIELDS:
                incoming = row.get(field)
                current = getattr(outcome, field)
                if cls._comparable(current) != cls._comparable(incoming):
                    raise CloudOutcomeSeedError(
                        f"Immutable snapshot mismatch for {outcome.symbol} "
                        f"{outcome.evaluation_session}: {field}"
                    )
            changed = []
            for field in OUTCOME_FIELDS:
                if field in IMMUTABLE_OUTCOME_FIELDS:
                    continue
                incoming = row.get(field)
                current = getattr(outcome, field)
                if incoming is None or cls._comparable(current) == cls._comparable(incoming):
                    continue
                if current is not None and field != "is_complete":
                    raise CloudOutcomeSeedError(
                        f"Refusing to overwrite forward label: {field}"
                    )
                if field == "is_complete" and bool(current) and not bool(incoming):
                    raise CloudOutcomeSeedError("Completed outcome cannot become pending.")
                setattr(outcome, field, incoming)
                changed.append(field)
            if changed:
                outcome.save(update_fields=[*changed, "updated_at"])
                outcomes_updated += 1
        return {
            "companies_created": companies_created,
            "outcomes_created": outcomes_created,
            "outcomes_updated": outcomes_updated,
        }

    @classmethod
    def verify_against(cls, source: Path) -> dict[str, int]:
        source = Path(source)
        payload = source.read_bytes()
        checksum_path = source.with_suffix(source.suffix + ".sha256")
        expected = checksum_path.read_text(encoding="ascii").strip().lower()
        if not expected or cls._digest(payload) != expected:
            raise CloudOutcomeSeedError("Seed checksum verification failed.")
        document = json.loads(payload)
        if document.get("schema_version") != SCHEMA_VERSION:
            raise CloudOutcomeSeedError("Unsupported seed schema version.")

        missing = mismatched = 0
        for row in document.get("outcomes", []):
            outcome = PreBreakoutSetupOutcome.objects.filter(
                symbol=row["symbol"], exchange=row["exchange"],
                evaluation_session=row["evaluation_session"],
            ).first()
            if outcome is None:
                missing += 1
                continue
            if any(
                cls._comparable(getattr(outcome, field))
                != cls._comparable(row.get(field))
                for field in OUTCOME_FIELDS
            ):
                mismatched += 1
        duplicates = (
            PreBreakoutSetupOutcome.objects.values(
                "symbol", "exchange", "evaluation_session"
            ).annotate(row_count=Count("id")).filter(row_count__gt=1).count()
        )
        if missing or mismatched or duplicates:
            raise CloudOutcomeSeedError(
                f"Seed verification failed: missing={missing} "
                f"mismatched={mismatched} duplicates={duplicates}"
            )
        return {
            "database_count": PreBreakoutSetupOutcome.objects.count(),
            "seed_count": len(document.get("outcomes", [])),
            "missing": missing,
            "mismatched": mismatched,
            "duplicates": duplicates,
        }
