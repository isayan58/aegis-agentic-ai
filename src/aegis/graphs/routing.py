"""Offline routing prototype with explicitly synthetic worker results."""

from datetime import datetime, timezone
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import ValidationError

from aegis.clarification import check_clarity
from aegis.nodes.planner import plan_deterministically
from aegis.schemas import (
    EvidenceItem,
    PlanStep,
    ResearchRequest,
    SourceRecord,
)
from aegis.state import (
    AegisState,
    RunStatus,
    bundle_from_state,
    make_evidence_id,
)


def validate_input(state: AegisState) -> dict:
    """Convert untrusted input into the shared request schema."""

    raw = state.get("raw_request")

    # Revalidate model instances too, rather than trusting mutations.
    if isinstance(raw, ResearchRequest):
        raw = raw.model_dump()

    try:
        request = ResearchRequest.model_validate(raw)
    except ValidationError:
        # Do not put raw inputs or exception details into shared errors.
        return {
            "status": RunStatus.FAILED,
            "errors": [
                {
                    "node": "validate_input",
                    "code": "invalid_request",
                    "message": "Input does not match ResearchRequest.",
                }
            ],
            "node_events": [
                {"node": "validate_input", "outcome": "invalid"}
            ],
        }

    return {
        "request": request,
        "status": RunStatus.RUNNING,
        "node_events": [
            {"node": "validate_input", "outcome": "valid"}
        ],
    }


def clarify_request(state: AegisState) -> dict:
    """Stop with questions when required request details are missing."""

    clarification = check_clarity(state["request"])

    status = (
        RunStatus.NEEDS_CLARIFICATION
        if clarification.needs_clarification
        else RunStatus.RUNNING
    )

    return {
        "clarification": clarification,
        "status": status,
        "node_events": [
            {
                "node": "clarify",
                "needs_clarification": clarification.needs_clarification,
            }
        ],
    }


def create_plan(state: AegisState) -> dict:
    """Use the tested deterministic planner for this offline graph."""

    plan = plan_deterministically(
        state["request"],
        retrieval_worker="evidence",
    )

    return {
        "plan": plan,
        "node_events": [
            {"node": "planner", "planned_steps": len(plan.steps)}
        ],
    }

def route_after_validation(
    state: AegisState,
) -> Literal["clarify", "__end__"]:
    """Pure routing decision: invalid input must stop."""

    if state["status"] == RunStatus.RUNNING:
        return "clarify"

    return END


def route_after_clarification(
    state: AegisState,
) -> Literal["planner", "__end__"]:
    """Pure routing decision: only complete requests reach planning."""

    if state["status"] == RunStatus.RUNNING:
        return "planner"

    return END


class WorkerInput(TypedDict):
    """The smaller payload supplied to each worker invocation."""

    task: PlanStep
    request: ResearchRequest


def route_to_workers(state: AegisState) -> list[Send]:
    """Dispatch independent evidence tasks, leaving analysis for later."""

    tasks = [
        step
        for step in state["plan"].steps
        if step.worker == "evidence"
    ]

    if not tasks:
        raise ValueError("Routing prototype requires evidence tasks")

    # This prototype supports only independent evidence tasks.
    # Reject dependencies instead of silently executing them too early.
    if any(task.depends_on for task in tasks):
        raise ValueError(
            "Evidence dependencies require a task scheduler"
        )

    return [
        Send(
            "stub_worker",
            {
                "task": task,
                "request": state["request"],
            },
        )
        for task in tasks
    ]

def stub_worker(payload: WorkerInput) -> dict:
    """Return labelled synthetic evidence to exercise parallel merging."""

    task = payload["task"]
    request = payload["request"]

    # Every worker emits the same immutable synthetic source record.
    # The fixed timestamp is test metadata, not a real retrieval time.
    source = SourceRecord(
        source_id="src_routing_stub_v1",
        title="Synthetic routing-test source",
        kind="dataset",
        dataset_ref="routing_stub_v1",
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_test_data=True,
    )

    evidence_id = make_evidence_id(
        source_id=source.source_id,
        locator=task.step_id,
        subject=task.subject,
        factor=task.factor,
        time_period=request.scope.time_period,
        coverage=request.scope.coverage,
    )

    evidence = EvidenceItem(
        evidence_id=evidence_id,
        source_id=source.source_id,
        subject=task.subject,
        factor=task.factor,
        excerpt=(
            "SYNTHETIC ROUTING STUB. No research was performed. "
            "This record proves only that the task was dispatched."
        ),
        locator=task.step_id,
        time_period=request.scope.time_period,
        coverage=request.scope.coverage,
    )

    # Return only this worker's contribution.
    # The existing merge_by_id and append reducers combine updates.
    return {
        "sources": {source.source_id: source},
        "evidence": {evidence.evidence_id: evidence},
        "node_events": [
            {
                "node": "stub_worker",
                "step_id": task.step_id,
                "subject": task.subject,
                "factor": task.factor,
            }
        ],
    }


def collect_results(state: AegisState) -> dict:
    """Validate the merged bundle and confirm every dispatch returned."""

    bundle = bundle_from_state(state)

    expected_tasks = {
        step.step_id
        for step in state["plan"].steps
        if step.worker == "evidence"
    }

    worker_events = [
        event
        for event in state.get("node_events", [])
        if event.get("node") == "stub_worker"
    ]

    completed_tasks = {
        event["step_id"] for event in worker_events
    }

    if (
        completed_tasks != expected_tasks
        or len(worker_events) != len(expected_tasks)
        or len(bundle.evidence) != len(expected_tasks)
    ):
        raise ValueError("Collected results do not match dispatched tasks")

    return {
        # Do not label the research completed: these are placeholders,
        # and the analysis tasks have not executed.
        "status": RunStatus.DEGRADED,
        "node_events": [
            {
                "node": "collect",
                "evidence_count": len(bundle.evidence),
                "source_count": len(bundle.sources),
                "stub_only": True,
                "pending_analysis_tasks": sum(
                    step.worker == "analysis"
                    for step in state["plan"].steps
                ),
            }
        ],
    }

def build_routing_graph():
    """Connect validation, clarification, planning, fan-out and join."""

    builder = StateGraph(AegisState)

    builder.add_node("validate_input", validate_input)
    builder.add_node("clarify", clarify_request)
    builder.add_node("planner", create_plan)

    # Each Send supplies WorkerInput rather than the full AegisState.
    builder.add_node("stub_worker", stub_worker)
    builder.add_node("collect", collect_results)

    builder.add_edge(START, "validate_input")

    builder.add_conditional_edges(
        "validate_input",
        route_after_validation,
        {"clarify": "clarify", END: END},
    )

    builder.add_conditional_edges(
        "clarify",
        route_after_clarification,
        {"planner": "planner", END: END},
    )

    builder.add_conditional_edges(
        "planner",
        route_to_workers,
        ["stub_worker"],
    )

    # All dispatched workers here execute in the same graph superstep.
    # Their updates merge before the collector runs.
    builder.add_edge("stub_worker", "collect")
    builder.add_edge("collect", END)

    return builder.compile()