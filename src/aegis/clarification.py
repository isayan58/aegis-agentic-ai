"""Check whether a research request needs more user instructions."""

from aegis.schemas import (
    ClarificationQuestion,
    ClarificationResult,
    ResearchRequest,
)


def check_clarity(request: ResearchRequest) -> ClarificationResult:
    """Return questions for missing factors, scope, or ranking preferences."""

    questions = []

    # Factors tell the research workers which aspects to investigate.
    if not request.factors:
        questions.append(
            ClarificationQuestion(
                field="factors",
                question=(
                    "Which aspects should the research focus on? "
                    "You can also ask Aegis to propose some for approval."
                ),
                reason=(
                    "The selected factors determine what evidence "
                    "we need to collect."
                ),
            )
        )

    # An explicit period prevents accidentally mixing incompatible dates.
    if request.scope.time_period is None:
        questions.append(
            ClarificationQuestion(
                field="scope.time_period",
                question=(
                    "What period should the research cover? "
                    "Specify a date range, an as-of date, "
                    "or say that time is not relevant."
                ),
                reason=(
                    "Evidence from different periods may not "
                    "support a fair comparison."
                ),
            )
        )

    # Coverage defines boundaries such as competitions, regions, or use cases.
    if request.scope.coverage is None:
        questions.append(
            ClarificationQuestion(
                field="scope.coverage",
                question=(
                    "What context or boundaries should apply? "
                    "For example: competitions, geography, use case, "
                    "or a general overview."
                ),
                reason=(
                    "Coverage determines which evidence belongs "
                    "in the research."
                ),
            )
        )

    # Ranking needs a decision rule; a descriptive comparison does not.
    if request.mode == "rank" and request.ranking_basis is None:
        questions.append(
            ClarificationQuestion(
                field="ranking_basis",
                question=(
                    "How should we decide the ranking? "
                    "State your priorities or provide factor weights."
                ),
                reason=(
                    "Choosing a winner requires an explicit "
                    "decision rule."
                ),
            )
        )

    # The result's needs_clarification property checks whether this list is empty.
    return ClarificationResult(questions=questions)