"""Regression tests for identifying missing research instructions."""

import pytest

from aegis.clarification import check_clarity
from aegis.schemas import ResearchRequest


@pytest.fixture
def complete_payload():
    """A comparison request with all clarification requirements satisfied."""

    return {
        "objective": "Compare fictional players.",
        "subjects": ["Player A", "Player B"],
        "factors": ["Scoring", "Creativity"],
        "mode": "compare",
        "scope": {
            "time_period": "2024–2025",
            "coverage": "Demo League",
        },
    }


def test_incomplete_request_gets_all_required_questions():
    """An incomplete but structurally valid request needs clarification."""

    request = ResearchRequest(
        objective="Compare fictional players.",
        subjects=["Player A", "Player B"],
        mode="compare",
    )

    result = check_clarity(request)
    fields = [question.field for question in result.questions]

    assert result.needs_clarification is True

    # Compare sorted lists so question order is not significant,
    # while duplicated questions would still cause a failure.
    assert sorted(fields) == [
        "factors",
        "scope.coverage",
        "scope.time_period",
    ]

    # Every question should explain both what is needed and why.
    assert all(question.question.strip() for question in result.questions)
    assert all(question.reason.strip() for question in result.questions)


@pytest.mark.parametrize(
    "missing_field",
    [
        "factors",
        "scope.time_period",
        "scope.coverage",
    ],
)
def test_one_missing_field_gets_one_question(
    complete_payload,
    missing_field,
):
    """A request should not receive unrelated clarification questions."""

    if missing_field == "factors":
        complete_payload.pop("factors")
    else:
        scope_field = missing_field.split(".", maxsplit=1)[1]
        complete_payload["scope"].pop(scope_field)

    request = ResearchRequest.model_validate(complete_payload)
    result = check_clarity(request)

    assert result.needs_clarification is True
    assert [question.field for question in result.questions] == [
        missing_field
    ]


def test_complete_comparison_needs_no_clarification(complete_payload):
    """A descriptive comparison does not require a ranking basis."""

    request = ResearchRequest.model_validate(complete_payload)
    result = check_clarity(request)

    assert result.needs_clarification is False
    assert result.questions == []


def test_rank_without_basis_gets_exactly_one_question(complete_payload):
    """Ranking requires an explicit decision rule."""

    complete_payload["mode"] = "rank"

    request = ResearchRequest.model_validate(complete_payload)
    result = check_clarity(request)

    assert result.needs_clarification is True
    assert len(result.questions) == 1
    assert result.questions[0].field == "ranking_basis"


def test_rank_with_basis_needs_no_clarification(complete_payload):
    """Supplying the ranking rule resolves the outstanding question."""

    complete_payload["mode"] = "rank"
    complete_payload["ranking_basis"] = (
        "Prioritize creativity; use scoring as a tiebreaker."
    )

    request = ResearchRequest.model_validate(complete_payload)
    result = check_clarity(request)

    assert result.needs_clarification is False
    assert result.questions == []