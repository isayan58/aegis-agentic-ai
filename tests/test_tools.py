"""Offline tests for fixture lookup, calculations, and tool interfaces."""

import math

import pytest
from pydantic import ValidationError

from aegis.schemas import ResearchBundle
from aegis.tools.calculators import (
    calculator,
    normalize,
    per_90,
    rank,
    sensitivity_check,
    weighted_score,
)
from aegis.tools.evidence import Fixture, load_fixture, lookup_evidence
from aegis.tools.registry import TOOLS


def test_fixtures_load():
    assert len(load_fixture("football_demo_v1").rows) == 6
    assert len(load_fixture("platforms_demo_v1").rows) == 3


def test_fixture_rejects_invalid_values():
    payload = load_fixture("football_demo_v1").model_dump()
    payload["rows"][0]["minutes"] = -1

    with pytest.raises(ValidationError):
        Fixture.model_validate(payload)


def test_fixture_rejects_duplicate_observations():
    payload = load_fixture("football_demo_v1").model_dump()
    payload["rows"].append(dict(payload["rows"][0]))

    with pytest.raises(ValidationError, match="Duplicate"):
        Fixture.model_validate(payload)


def test_loader_rejects_unapproved_paths():
    with pytest.raises(ValueError, match="Unknown fixture"):
        load_fixture("../../.env")


@pytest.mark.parametrize(
    "subject,factor,reference,count",
    [
        ("Player A", "Scoring", "football_demo_v1", 2),
        ("Vendor A", "Operating cost", "platforms_demo_v1", 1),
    ],
)
def test_lookup_has_valid_references(subject, factor, reference, count):
    result = lookup_evidence(subject, factor, reference)

    assert result.reason is None
    assert result.source is not None

    bundle = ResearchBundle(
        sources=[result.source],
        evidence=result.evidence,
    )

    assert len(bundle.evidence) == count
    assert result.source.is_test_data is True


def test_lookup_has_stable_ids():
    first = lookup_evidence("Player A", "Scoring", "football_demo_v1")
    second = lookup_evidence(" player a ", "scoring", "football_demo_v1")

    assert [item.evidence_id for item in first.evidence] == [
        item.evidence_id for item in second.evidence
    ]


@pytest.mark.parametrize(
    "subject,factor",
    [
        ("Unknown Player", "Scoring"),
        ("Player A", "Unknown Factor"),
    ],
)
def test_lookup_reports_gaps(subject, factor):
    result = lookup_evidence(subject, factor, "football_demo_v1")

    assert result.source is None
    assert result.evidence == []
    assert result.reason


def test_per_90():
    assert per_90(12, 1800) == pytest.approx(0.6)


@pytest.mark.parametrize(
    "value,minutes",
    [(1, 0), (1, -90), (-1, 90), (math.nan, 90)],
)
def test_per_90_rejects_invalid_inputs(value, minutes):
    with pytest.raises(ValueError):
        per_90(value, minutes)


def test_normalization_directions_and_ties():
    values = {"A": 10, "B": 20, "C": 30}

    assert normalize(values, "higher") == {
        "A": 0.0, "B": 0.5, "C": 1.0
    }

    assert normalize(values, "lower") == {
        "A": 1.0, "B": 0.5, "C": 0.0
    }

    assert normalize({"A": 7, "B": 7}, "higher") == {
        "A": 0.5, "B": 0.5
    }


def test_weighted_score():
    assert weighted_score(
        {"quality": 0.8, "cost": 0.4},
        {"quality": 0.75, "cost": 0.25},
    ) == pytest.approx(0.7)


@pytest.mark.parametrize(
    "scores,weights",
    [
        ({"a": 0.5}, {"a": 0.8}),
        ({"a": 0.5}, {"b": 1.0}),
        ({"a": 1.5}, {"a": 1.0}),
        ({"a": 0.5, "b": 0.5}, {"a": -0.1, "b": 1.1}),
    ],
)
def test_weighted_score_rejects_invalid_inputs(scores, weights):
    with pytest.raises(ValueError):
        weighted_score(scores, weights)


def test_rank_preserves_ties():
    result = rank({"B": 0.8, "A": 0.8, "C": 0.2})

    assert [row["subject"] for row in result] == ["A", "B", "C"]
    assert [row["rank"] for row in result] == [1, 1, 3]


def test_sensitivity_detects_change():
    result = sensitivity_check(
        {
            "A": {"quality": 1.0, "cost": 0.0},
            "B": {"quality": 0.0, "cost": 1.0},
        },
        {"quality": 0.5, "cost": 0.5},
    )

    assert result["base_winners"] == ["A", "B"]
    assert result["winner_changed"] is True
    assert len(result["scenarios"]) == 4

    for scenario in result["scenarios"]:
        assert sum(scenario["weights"].values()) == pytest.approx(1)


def test_sensitivity_recognizes_stable_winner():
    result = sensitivity_check(
        {
            "A": {"quality": 0.9, "cost": 0.8},
            "B": {"quality": 0.3, "cost": 0.2},
        },
        {"quality": 0.5, "cost": 0.5},
    )

    assert result["base_winners"] == ["A"]
    assert result["winner_changed"] is False


def test_calculator_arithmetic():
    assert calculator("(20 * 2) + (2 * 100)") == 240
    assert calculator("-3 + 10 / 2") == 2


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "open('secret.txt')",
        "x + 1",
        "(1).__class__",
        "2 ** 10",
        "1 / 0",
        "True + 1",
        "[1, 2]",
        "1 +",
        "1e309",
    ],
)
def test_calculator_rejects_unsafe_or_invalid_input(expression):
    with pytest.raises(ValueError):
        calculator(expression)


def test_all_tool_wrappers_can_be_invoked():
    arguments = {
        "load_fixture_tool": {
            "dataset_ref": "football_demo_v1",
        },
        "lookup_evidence_tool": {
            "subject": "Player A",
            "factor": "Scoring",
            "dataset_ref": "football_demo_v1",
        },
        "per_90_tool": {
            "value": 12,
            "minutes": 1800,
        },
        "normalize_tool": {
            "values": {"A": 1, "B": 2},
            "direction": "higher",
        },
        "weighted_score_tool": {
            "scores": {"quality": 0.8},
            "weights": {"quality": 1.0},
        },
        "rank_tool": {
            "scores": {"A": 0.8, "B": 0.2},
        },
        "sensitivity_check_tool": {
            "scores": {
                "A": {"quality": 0.8},
                "B": {"quality": 0.2},
            },
            "weights": {"quality": 1.0},
        },
        "calculator_tool": {
            "expression": "2 + 3",
        },
    }

    assert {item.name for item in TOOLS} == set(arguments)

    for item in TOOLS:
        assert item.invoke(arguments[item.name]) is not None