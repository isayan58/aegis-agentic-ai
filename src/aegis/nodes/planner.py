"""Build and validate research plans before worker execution."""

from typing import Literal

from aegis.clarification import check_clarity
from aegis.schemas import (
    PlanStep,
    ResearchPlan,
    ResearchRequest,
    validate_plan_against_request,
)
import json
from langchain_core.runnables import RunnableConfig
from aegis.llm.gateway import get_model


def plan_deterministically(
    request: ResearchRequest,
    *,
    retrieval_worker: Literal["evidence", "web"] = "evidence",
) -> ResearchPlan:
    """Create one retrieval and one analysis task per subject/factor.

    The caller selects the retrieval route explicitly.
    This function does not infer whether a dataset has the requested data.
    """

    request = ResearchRequest.model_validate(request.model_dump())

    # Type hints don't enforce values at runtime.
    if retrieval_worker not in {"evidence", "web"}:
        raise ValueError("Retrieval worker must be evidence or web")

    clarification = check_clarity(request)

    if clarification.needs_clarification:
        fields = [
            question.field
            for question in clarification.questions
        ]
        raise ValueError(f"Clarification required for: {fields}")

    steps = []

    for subject_index, subject in enumerate(request.subjects, start=1):
        for factor_index, factor in enumerate(request.factors, start=1):
            # Indices avoid collisions caused by converting names into
            # slugs, such as "A B" and "A-B" becoming the same text.
            # These IDs are deterministic within the ordered request.
            suffix = f"s{subject_index}:f{factor_index}"
            retrieval_id = f"{retrieval_worker}:{suffix}"

            steps.append(
                PlanStep(
                    step_id=retrieval_id,
                    worker=retrieval_worker,
                    subject=subject,
                    factor=factor,
                    depends_on=[],
                )
            )

            steps.append(
                PlanStep(
                    step_id=f"analysis:{suffix}",
                    worker="analysis",
                    subject=subject,
                    factor=factor,
                    depends_on=[retrieval_id],
                )
            )

    plan = ResearchPlan(
        steps=steps,
        rationale=(
            f"Collect each requested subject/factor using the "
            f"{retrieval_worker} worker, then analyse each pair "
            "after its evidence collection finishes."
        ),
    )

    # Both deterministic and LLM plans will pass through this gate.
    return validate_plan_against_request(plan, request)

PLANNER_SYSTEM_PROMPT = """
You create research task plans. Do not perform the research.

The input contains:
- request: the user's validated research request
- retrieval_worker: the retrieval route selected for this experiment

Rules:
1. Preserve the requested subject and factor names exactly.
2. Create exactly one retrieval task for every subject/factor pair.
3. Use the supplied retrieval_worker for every retrieval task.
4. Retrieval tasks have no dependencies.
5. Create exactly one analysis task for every subject/factor pair.
6. Each analysis task depends on its matching retrieval task.
7. Use unique step IDs and reference them exactly in depends_on.
8. Do not introduce extra subjects or factors.
9. Do not create dependency cycles.
10. Explain the plan briefly in rationale.

This is a planning exercise. Do not invent observations, claim that
evidence exists, or claim that any task has already executed.

The caller retains the original request, including its time period,
coverage, constraints and ranking basis, for subsequent workers.
"""


def plan_with_llm(
    request: ResearchRequest,
    *,
    config: RunnableConfig,
    retrieval_worker: Literal["evidence", "web"] = "evidence",
) -> ResearchPlan:
    """Generate a plan with the planner model and validate its coverage."""

    request = ResearchRequest.model_validate(request.model_dump())

    if retrieval_worker not in {"evidence", "web"}:
        raise ValueError("Retrieval worker must be evidence or web")

    # Reject incomplete requests before making a paid model call.
    clarification = check_clarity(request)

    if clarification.needs_clarification:
        fields = [
            question.field
            for question in clarification.questions
        ]
        raise ValueError(f"Clarification required for: {fields}")

    structured_model = get_model("planner").with_structured_output(
        ResearchPlan,
        method="function_calling",
        include_raw=False,
    )

    payload = {
        "request": request.model_dump(mode="json"),
        "retrieval_worker": retrieval_worker,
    }

    # The caller supplies the budget callback configuration.
    # It is passed through to the underlying model invocation.
    plan = structured_model.invoke(
        [
            ("system", PLANNER_SYSTEM_PROMPT),
            ("human", json.dumps(payload)),
        ],
        config=config,
    )

    # Pydantic checks internal dependencies during output parsing.
    # This additional gate checks coverage against the original request.
    plan = validate_plan_against_request(plan, request)

    # For this controlled experiment, require the requested route and
    # exactly one retrieval + analysis task per subject/factor.
    expected_tasks = {
        (worker, subject.casefold(), factor.casefold())
        for subject in request.subjects
        for factor in request.factors
        for worker in (retrieval_worker, "analysis")
    }

    actual_tasks = [
        (step.worker, step.subject.casefold(), step.factor.casefold())
        for step in plan.steps
    ]

    if (
        set(actual_tasks) != expected_tasks
        or len(actual_tasks) != len(expected_tasks)
    ):
        raise ValueError(
            "LLM plan must contain exactly one retrieval and one "
            "analysis task per requested subject/factor"
        )

    steps_by_id = {step.step_id: step for step in plan.steps}

    for step in plan.steps:
        if step.worker == retrieval_worker:
            if step.depends_on:
                raise ValueError(
                    "Retrieval tasks must have no dependencies"
                )
        else:
            if len(step.depends_on) != 1:
                raise ValueError(
                    "Analysis must have exactly one retrieval dependency"
                )

            dependency = steps_by_id[step.depends_on[0]]

            if dependency.worker != retrieval_worker:
                raise ValueError(
                    "Analysis dependency uses the wrong retrieval route"
                )

    return plan