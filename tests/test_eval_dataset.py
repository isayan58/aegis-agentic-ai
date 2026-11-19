"""Check dataset coverage and ensure the evaluator detects regressions."""

from collections import Counter

import pytest

from evals.runner import evaluate_case, load_cases, parse_cases


CASES = load_cases()


def test_dataset_has_the_planned_30_cases():
    """Protect both the original checks and Day 3 coverage."""

    assert len(CASES) == 30

    assert Counter(case.category for case in CASES) == {
        "valid": 21,
        "clarification": 4,
        "invalid": 3,
        "reference": 2,
    }

    assert len({case.id for case in CASES}) == 30

    # Preserve the original three numerical checks.
    assert sum(len(case.input.tools) for case in CASES) == 3

    # Day 3 adds explicit routing and agent-tool expectations.
    assert sum(bool(case.expected.workers) for case in CASES) == 15
    assert sum(bool(case.expected.tool_sequence) for case in CASES) == 15


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_evaluation_case_passes(case):
    """Run each evaluation as a separately named pytest case."""

    result = evaluate_case(case)

    assert result["passed"], result["failures"]


def test_evaluator_detects_an_incorrect_numeric_expectation():
    """Prove that the evaluator does not blindly mark a case as passed."""

    original = next(
        case for case in CASES
        if case.id == "football_research"
    )

    # Copy the case so the original dataset remains unchanged.
    changed = original.model_copy(deep=True)
    changed.expected.tool_outputs = [999.0]

    result = evaluate_case(changed)

    assert result["passed"] is False
    assert any(
        "Tool output" in failure
        for failure in result["failures"]
    )


def test_dataset_rejects_duplicate_ids():
    """Duplicate IDs would make historical results ambiguous."""

    line = CASES[0].model_dump_json()

    with pytest.raises(ValueError, match="Duplicate evaluation ID"):
        parse_cases(f"{line}\n{line}\n")


def test_dataset_rejects_malformed_json():
    """Broken dataset definitions must not be silently skipped."""

    with pytest.raises(ValueError, match="line 1"):
        parse_cases("{not valid json}")


def test_dataset_rejects_empty_content():
    with pytest.raises(ValueError, match="empty"):
        parse_cases("\n\n")