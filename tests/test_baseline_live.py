"""Explicitly enabled live test for the single-agent baseline."""

import json
from decimal import Decimal

import pytest

from aegis.graphs.baseline import run_baseline_with_details
from aegis.schemas import ResearchRequest, ResearchScope


@pytest.mark.live
def test_baseline_football_comparison():
    """Verify real tool use, known values and correctly scoped citations."""

    request = ResearchRequest(
        objective=(
            "Compare Player A and Player B by total goals in the "
            "2025 Demo League. Return one comparison row per player "
            "with factor='scoring', unit='goals', and the numeric goal "
            "total. Do not rank them."
        ),
        subjects=["Player A", "Player B"],
        factors=["scoring"],
        mode="compare",
        scope=ResearchScope(
            time_period="2025",
            coverage="Demo League",
        ),
    )

    run = run_baseline_with_details(
        request,
        dataset_ref="football_demo_v1",
        budget_usd=Decimal("0.05"),
        case_id="live_football_compare",
    )

    assert run.report.status == "completed"
    assert run.report.mode == "compare"
    assert run.report.ranking == []
    assert run.report.citations
    assert len(run.tracker.calls) > 0
    assert run.tracker.spent_usd > 0

    # Assert the exact requested observations, not just valid JSON.
    assert len(run.report.comparison_rows) == 2
    rows = {
        row.subject: row
        for row in run.report.comparison_rows
    }
    assert set(rows) == {"Player A", "Player B"}

    evidence_by_id = {
        item.evidence_id: item
        for item in run.bundle.evidence
    }

    for subject, expected_goals in {
        "Player A": 14,
        "Player B": 11,
    }.items():
        row = rows[subject]

        assert row.factor == "scoring"
        assert row.unit == "goals"
        assert isinstance(row.value, float)
        assert row.value == pytest.approx(expected_goals)

        # Existing IDs alone aren't sufficient: ensure the citations
        # point to the correct player, season and competition.
        assert row.evidence_ids

        for evidence_id in row.evidence_ids:
            evidence = evidence_by_id[evidence_id]

            assert evidence.subject == subject
            assert evidence.factor == "scoring"
            assert evidence.time_period == "2025"
            assert evidence.coverage == "Demo League"

            observation = json.loads(evidence.excerpt)
            assert observation["goals"] == expected_goals