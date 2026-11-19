"""Offline checks for routing, parallel dispatch and collection."""

from copy import deepcopy

import pytest
from langgraph.graph import END

from aegis.graphs.routing import (
    build_routing_graph,
    route_after_clarification,
    route_after_validation,
    route_to_workers,
)
from aegis.nodes.planner import plan_deterministically
from aegis.schemas import ResearchRequest
from aegis.state import RunStatus, bundle_from_state


@pytest.fixture
def raw_request():
    """Return fresh input for every test."""

    return {
        "objective": "Compare three fictional players.",
        "subjects": ["Player A", "Player B", "Player C"],
        "factors": ["scoring", "creativity"],
        "mode": "compare",
        "scope": {
            "time_period": "2025",
            "coverage": "Demo League",
        },
    }


@pytest.fixture
def graph():
    """Compile a fresh graph without making any provider calls."""

    return build_routing_graph()


def test_validation_router():
    """Only valid input should continue to clarification."""

    assert route_after_validation(
        {"status": RunStatus.RUNNING}
    ) == "clarify"

    assert route_after_validation(
        {"status": RunStatus.FAILED}
    ) == END


def test_clarification_router():
    """Questions must stop execution before planning."""

    assert route_after_clarification(
        {"status": RunStatus.RUNNING}
    ) == "planner"

    assert route_after_clarification(
        {"status": RunStatus.NEEDS_CLARIFICATION}
    ) == END


def test_worker_router_dispatches_each_pair(raw_request):
    """Dispatch retrieval tasks only, with the original request context."""

    request = ResearchRequest.model_validate(raw_request)
    plan = plan_deterministically(request)
    original_plan = plan.model_dump()

    dispatches = route_to_workers({
        "request": request,
        "plan": plan,
    })

    assert len(dispatches) == 6
    assert all(send.node == "stub_worker" for send in dispatches)

    actual_pairs = {
        (
            send.arg["task"].subject,
            send.arg["task"].factor,
        )
        for send in dispatches
    }

    assert actual_pairs == {
        (subject, factor)
        for subject in raw_request["subjects"]
        for factor in raw_request["factors"]
    }

    for send in dispatches:
        assert send.arg["task"].worker == "evidence"
        assert send.arg["request"] == request

    # A router should not mutate the plan while selecting destinations.
    assert plan.model_dump() == original_plan


def test_valid_request_fans_out_and_collects(graph, raw_request):
    """All worker updates must survive merging, with one collection."""

    original_input = deepcopy(raw_request)
    result = graph.invoke({"raw_request": raw_request})

    bundle = bundle_from_state(result)
    events = result["node_events"]

    worker_events = [
        event for event in events
        if event["node"] == "stub_worker"
    ]
    collector_events = [
        event for event in events
        if event["node"] == "collect"
    ]

    assert len(worker_events) == 6
    assert len({event["step_id"] for event in worker_events}) == 6
    assert len(bundle.evidence) == 6
    assert len(bundle.sources) == 1
    assert len(collector_events) == 1

    # The graph collected placeholders; research is not complete.
    assert result["status"] == RunStatus.DEGRADED
    assert collector_events[0]["stub_only"] is True
    assert collector_events[0]["pending_analysis_tasks"] == 6
    assert bundle.sources[0].is_test_data is True
    assert result.get("report") is None

    # Every requested pair must appear in the merged evidence.
    assert {
        (item.subject, item.factor)
        for item in bundle.evidence
    } == {
        (subject, factor)
        for subject in raw_request["subjects"]
        for factor in raw_request["factors"]
    }

    assert raw_request == original_input


def test_incomplete_request_stops_before_planning(graph, raw_request):
    """A structurally valid request can still require clarification."""

    raw_request["factors"] = []

    result = graph.invoke({"raw_request": raw_request})

    assert result["status"] == RunStatus.NEEDS_CLARIFICATION

    assert {
        question.field
        for question in result["clarification"].questions
    } == {"factors"}

    # No planner, worker or collector should execute.
    assert [
        event["node"] for event in result["node_events"]
    ] == ["validate_input", "clarify"]

    assert not result.get("evidence")
    assert result.get("plan") is None


def test_invalid_request_stops_at_validation(graph, raw_request):
    """Compare mode with only one subject is structurally invalid."""

    raw_request["subjects"] = ["Player A"]

    result = graph.invoke({"raw_request": raw_request})

    assert result["status"] == RunStatus.FAILED
    assert result["errors"][0]["code"] == "invalid_request"

    assert [
        event["node"] for event in result["node_events"]
    ] == ["validate_input"]

    assert not result.get("evidence")
    assert result.get("plan") is None


def test_validation_error_does_not_echo_input(graph, raw_request):
    """Error records must not copy untrusted request values."""

    marker = "PRIVATE_TEST_MARKER_DO_NOT_ECHO"

    # Unknown fields are rejected by ResearchRequest.
    raw_request["unexpected_field"] = marker

    result = graph.invoke({"raw_request": raw_request})

    assert result["status"] == RunStatus.FAILED
    assert marker not in repr(result["errors"])
    assert marker not in repr(result["node_events"])


def test_independent_invocations_do_not_accumulate_results(
    graph,
    raw_request,
):
    """Reusing the compiled graph must not mix separate runs."""

    first = graph.invoke({"raw_request": raw_request})
    second = graph.invoke({"raw_request": raw_request})

    for result in (first, second):
        workers = [
            event for event in result["node_events"]
            if event["node"] == "stub_worker"
        ]

        assert len(workers) == 6
        assert len(result["evidence"]) == 6

    # Identical tasks produce stable evidence IDs.
    assert set(first["evidence"]) == set(second["evidence"])