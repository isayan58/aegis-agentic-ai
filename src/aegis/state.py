"""Shared state and validation helpers for Aegis research runs."""

import hashlib
import json
from enum import Enum
from typing import Annotated, TypedDict

from aegis.reducers import (
    UsageTotals,
    append,
    merge_by_id,
    sum_usage,
)
from aegis.schemas import (
    ClarificationResult,
    EvidenceItem,
    ResearchBundle,
    ResearchFinding,
    ResearchRequest,
    SourceRecord,
    ResearchPlan
)


class RunStatus(str, Enum):
    """Recognized lifecycle states for a research run."""

    RUNNING = "running"
    NEEDS_CLARIFICATION = "needs_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    DEGRADED = "degraded"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


class AegisState(TypedDict, total=False):
    """Shared channels passed between graph nodes."""

    # Single-writer fields: the incoming value replaces the old value.
    request: ResearchRequest
    clarification: ClarificationResult | None

    # These contracts will become specific Pydantic models when
    # we implement planning, verification, approval, and reporting.
    # The planner now has a concrete, validated output contract.
    plan: ResearchPlan
    verification: dict[str, object] | None
    approval: dict[str, object] | None
    report: dict[str, object] | None

    status: RunStatus
    retry_count: int

    # Multiple workers can contribute distinct records.
    sources: Annotated[
        dict[str, SourceRecord],
        merge_by_id,
    ]

    evidence: Annotated[
        dict[str, EvidenceItem],
        merge_by_id,
    ]

    findings: Annotated[
        dict[str, ResearchFinding],
        merge_by_id,
    ]

    calculations: Annotated[
        dict[str, dict[str, object]],
        merge_by_id,
    ]

    # Workers emit new usage only, not accumulated totals.
    usage: Annotated[
        dict[str, UsageTotals],
        sum_usage,
    ]

    # Diagnostic history preserves entries from every worker.
    errors: Annotated[
        list[dict[str, object]],
        append,
    ]

    node_events: Annotated[
        list[dict[str, object]],
        append,
    ]

    # Untrusted input enters here; validation produces request.
    raw_request: object


def make_evidence_id(
    source_id: str,
    locator: str,
    subject: str,
    factor: str,
    *,
    time_period: str | None = None,
    coverage: str | None = None,
) -> str:
    """Create a stable ID for one observation within a source."""

    required = (source_id, locator, subject, factor)

    for value in required:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "Evidence identity fields must be non-empty strings"
            )

    for value in (time_period, coverage):
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    "Evidence scope must be non-empty text or None"
                )

    # Include the context that distinguishes one observation
    # from another within the same source.
    identity = [
        value.strip() if isinstance(value, str) else value
        for value in (
            source_id,
            locator,
            subject,
            factor,
            time_period,
            coverage,
        )
    ]

    # JSON preserves field boundaries without ambiguous separators.
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    return f"ev_{digest}"


def bundle_from_state(state: AegisState) -> ResearchBundle:
    """Validate records and references after workers have joined."""

    payload = {}

    channels = (
        ("sources", SourceRecord, "source_id"),
        ("evidence", EvidenceItem, "evidence_id"),
        ("findings", ResearchFinding, "finding_id"),
    )

    for channel, model_class, id_field in channels:
        records = []

        for key, value in state.get(channel, {}).items():
            if not isinstance(key, str):
                raise ValueError(
                    f"{channel} dictionary keys must be strings"
                )

            # Support both model instances and serialized dictionaries.
            # Dump existing models so their values are revalidated.
            raw = (
                value.model_dump()
                if isinstance(value, model_class)
                else value
            )

            record = model_class.model_validate(raw)

            # Prevent the lookup key from disagreeing with the record.
            if key != getattr(record, id_field):
                raise ValueError(
                    f"{channel} dictionary key does not match {id_field}"
                )

            records.append(record)

        # Stable ordering makes output easier to compare across runs.
        payload[channel] = sorted(
            records,
            key=lambda record: getattr(record, id_field),
        )

    # Your existing ResearchBundle validators check foreign references.
    return ResearchBundle.model_validate(payload)