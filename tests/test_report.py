"""Check report structure and references using the Day 2 fixture."""

import json

import pytest
from pydantic import ValidationError

from aegis.schemas import (
    ComparisonRow,
    FinalReport,
    ResearchBundle,
    validate_report_against_bundle,
)
from aegis.tools.evidence import lookup_evidence


@pytest.fixture
def report_and_bundle():
    """Build an independent report and evidence bundle for each test."""

    sources_by_id = {}
    evidence = []
    rows = []

    for subject in ["Player A", "Player B"]:
        lookup = lookup_evidence(
            subject=subject,
            factor="scoring",
            dataset_ref="football_demo_v1",
        )

        assert lookup.source is not None
        sources_by_id[lookup.source.source_id] = lookup.source

        # Keep the comparison scoped to one season.
        item = next(
            item
            for item in lookup.evidence
            if item.time_period == "2025"
        )
        evidence.append(item)

        observation = json.loads(item.excerpt)

        rows.append(
            ComparisonRow(
                subject=subject,
                factor="scoring",
                value=observation["goals"],
                unit="goals",
                evidence_ids=[item.evidence_id],
            )
        )

    bundle = ResearchBundle(
        sources=list(sources_by_id.values()),
        evidence=evidence,
    )

    report = FinalReport(
        summary="Comparison of fictional 2025 goal totals.",
        mode="compare",
        subjects=["Player A", "Player B"],
        comparison_rows=rows,
        limitations=["Synthetic data from the 2025 Demo League."],
        citations=list(sources_by_id),
        status="completed",
    )

    return report, bundle


def test_valid_report_passes(report_and_bundle):
    """A report referencing collected evidence should be accepted."""

    report, bundle = report_and_bundle

    validated = validate_report_against_bundle(report, bundle)

    assert validated == report


def test_unknown_evidence_is_rejected(report_and_bundle):
    """A plausible-looking but invented evidence ID must fail."""

    report, bundle = report_and_bundle
    report.comparison_rows[0].evidence_ids = ["ev_nonexistent"]

    with pytest.raises(ValueError, match="unknown evidence"):
        validate_report_against_bundle(report, bundle)


def test_unknown_source_is_rejected(report_and_bundle):
    """Bibliography entries must identify collected sources."""

    report, bundle = report_and_bundle
    report.citations.append("src_nonexistent")

    with pytest.raises(ValueError, match="unknown sources"):
        validate_report_against_bundle(report, bundle)


def test_missing_bibliography_source_is_rejected(report_and_bundle):
    """Valid evidence still needs its source in the bibliography."""

    report, bundle = report_and_bundle
    report.citations = []

    with pytest.raises(ValueError, match="missing sources"):
        validate_report_against_bundle(report, bundle)


def test_rank_mode_requires_ranking(report_and_bundle):
    """Changing the mode to rank requires actual ranking entries."""

    report, _ = report_and_bundle
    payload = report.model_dump()
    payload["mode"] = "rank"

    with pytest.raises(ValidationError, match="requires a ranking"):
        FinalReport.model_validate(payload)


def test_compare_mode_forbids_ranking(report_and_bundle):
    """Comparison mode must not silently become a ranking."""

    report, _ = report_and_bundle
    payload = report.model_dump()

    payload["ranking"] = [
        {
            "position": 1,
            "subject": "Player A",
            "score": 14.0,
            "evidence_ids": report.comparison_rows[0].evidence_ids,
        }
    ]

    with pytest.raises(
        ValidationError,
        match="Ranking is only allowed in rank mode",
    ):
        FinalReport.model_validate(payload)