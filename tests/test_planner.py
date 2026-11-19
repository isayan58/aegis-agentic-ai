"""Offline tests for deterministic planning and plan validation."""

import pytest
from pydantic import ValidationError

from aegis.nodes.planner import plan_deterministically
from aegis.schemas import (
    ResearchPlan,
    ResearchRequest,
    ResearchScope,
    validate_plan_against_request,
)


@pytest.fixture
def research_request():
    """Provide a fresh, complete request for each test."""

    return ResearchRequest(
        objective="Compare two players on scoring and creativity.",
        subjects=["Player A", "Player B"],
        factors=["scoring", "creativity"],
        mode="compare",
        scope=ResearchScope(
            time_period="2025",
            coverage="Demo League",
        ),
    )


def test_plan_covers_every_requested_pair(research_request):
    """Every subject/factor combination needs evidence collection."""

    plan = plan_deterministically(research_request)

    actual_pairs = {
        (step.subject, step.factor)
        for step in plan.steps
        if step.worker == "evidence"
    }

    assert actual_pairs == {
        ("Player A", "scoring"),
        ("Player A", "creativity"),
        ("Player B", "scoring"),
        ("Player B", "creativity"),
    }

    assert len(plan.steps) == 8
    assert validate_plan_against_request(plan, research_request) == plan


def test_analysis_depends_on_matching_evidence(research_request):
    """Analysis must wait for evidence about its own subject/factor."""

    plan = plan_deterministically(research_request)
    steps_by_id = {step.step_id: step for step in plan.steps}

    for step in plan.steps:
        if step.worker != "analysis":
            continue

        assert len(step.depends_on) == 1

        prerequisite = steps_by_id[step.depends_on[0]]

        assert prerequisite.worker == "evidence"
        assert prerequisite.subject == step.subject
        assert prerequisite.factor == step.factor


def test_repeated_planning_is_deterministic(research_request):
    """The same request and route should produce the same plan."""

    first = plan_deterministically(research_request)
    second = plan_deterministically(research_request)

    assert first.model_dump() == second.model_dump()


def test_explicit_web_route(research_request):
    """Web routing must be an explicit, supported alternative."""

    plan = plan_deterministically(
        research_request,
        retrieval_worker="web",
    )

    assert sum(step.worker == "web" for step in plan.steps) == 4
    assert all(step.worker != "evidence" for step in plan.steps)

    # The shared validator must accept web-backed analysis too.
    validate_plan_against_request(plan, research_request)


def test_incomplete_request_requires_clarification(research_request):
    """Don't plan work while required request details are missing."""

    payload = research_request.model_dump()
    payload["factors"] = []
    incomplete_request = ResearchRequest.model_validate(payload)

    with pytest.raises(ValueError, match="Clarification required"):
        plan_deterministically(incomplete_request)


def test_duplicate_step_ids_are_rejected(research_request):
    """Duplicate task IDs would make dependencies ambiguous."""

    payload = plan_deterministically(research_request).model_dump()

    # Append an exact copy so two tasks have the same ID.
    payload["steps"].append(dict(payload["steps"][0]))

    with pytest.raises(ValidationError, match="step IDs must be unique"):
        ResearchPlan.model_validate(payload)


def test_unknown_dependency_is_rejected(research_request):
    """A task cannot depend on a nonexistent task."""

    payload = plan_deterministically(research_request).model_dump()
    payload["steps"][0]["depends_on"] = ["task-that-does-not-exist"]

    with pytest.raises(ValidationError, match="unknown dependencies"):
        ResearchPlan.model_validate(payload)


def test_dependency_cycle_is_rejected(research_request):
    """Mutually dependent tasks could never become ready."""

    payload = plan_deterministically(research_request).model_dump()

    retrieval = next(
        step for step in payload["steps"]
        if step["worker"] == "evidence"
    )
    analysis = next(
        step for step in payload["steps"]
        if step["worker"] == "analysis"
        and retrieval["step_id"] in step["depends_on"]
    )

    # Analysis already depends on retrieval.
    # Making retrieval depend on analysis creates a cycle.
    retrieval["depends_on"] = [analysis["step_id"]]

    with pytest.raises(ValidationError, match="dependency cycle"):
        ResearchPlan.model_validate(payload)


def test_analysis_without_dependency_is_rejected(research_request):
    """Analysis cannot run before collecting its evidence."""

    payload = plan_deterministically(research_request).model_dump()

    analysis = next(
        step for step in payload["steps"]
        if step["worker"] == "analysis"
    )
    analysis["depends_on"] = []

    with pytest.raises(
        ValidationError,
        match="requires matching evidence or web dependency",
    ):
        ResearchPlan.model_validate(payload)


def test_analysis_with_wrong_evidence_is_rejected(research_request):
    """An existing dependency can still concern the wrong subject."""

    payload = plan_deterministically(research_request).model_dump()

    analysis = next(
        step for step in payload["steps"]
        if step["worker"] == "analysis"
        and step["subject"] == "Player A"
        and step["factor"] == "scoring"
    )

    wrong_retrieval = next(
        step for step in payload["steps"]
        if step["worker"] == "evidence"
        and step["subject"] == "Player B"
        and step["factor"] == "scoring"
    )

    analysis["depends_on"] = [wrong_retrieval["step_id"]]

    with pytest.raises(
        ValidationError,
        match="requires matching evidence or web dependency",
    ):
        ResearchPlan.model_validate(payload)


def test_missing_requested_pair_is_rejected(research_request):
    """An internally valid plan can still omit requested work."""

    payload = plan_deterministically(research_request).model_dump()

    # Remove both tasks for one pair. This avoids broken dependencies,
    # allowing us to test request coverage specifically.
    payload["steps"] = [
        step
        for step in payload["steps"]
        if not (
            step["subject"] == "Player B"
            and step["factor"] == "creativity"
        )
    ]

    incomplete_plan = ResearchPlan.model_validate(payload)

    with pytest.raises(ValueError, match="missing evidence collection"):
        validate_plan_against_request(
            incomplete_plan,
            research_request,
        )


def test_unrequested_subject_is_rejected(research_request):
    """The planner must not silently introduce another subject."""

    payload = plan_deterministically(research_request).model_dump()

    # Rename the subject in both retrieval and analysis tasks.
    # Dependencies remain internally consistent.
    for step in payload["steps"]:
        if step["subject"] == "Player B":
            step["subject"] = "Player C"

    expanded_plan = ResearchPlan.model_validate(payload)

    with pytest.raises(ValueError, match="unrequested subject/factor"):
        validate_plan_against_request(
            expanded_plan,
            research_request,
        )