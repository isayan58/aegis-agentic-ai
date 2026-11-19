"""Validated data structures shared across the Aegis application."""

from datetime import date
from typing import Annotated, Literal
from graphlib import CycleError, TopologicalSorter

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

# Shared text type: trims whitespace and rejects empty strings.
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

class ResearchScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_period: NonEmptyText | None = None
    coverage: NonEmptyText | None = None


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: NonEmptyText
    # Prototype limits to keep research runs manageable.
    subjects: list[NonEmptyText] = Field(
        min_length=1,
        max_length=5,
    )
    # Empty means the factors still need clarification or proposal.
    factors: list[NonEmptyText] = Field(
        default_factory=list,
        max_length=10,
    )
    mode: Literal["research", "compare", "rank"] = "research"
    scope: ResearchScope = Field(default_factory=ResearchScope)
    constraints: list[NonEmptyText] = Field(default_factory=list)
    ranking_basis: NonEmptyText | None = None


    @model_validator(mode="after")
    def validate_consistency(self):
        subject_keys = [name.casefold() for name in self.subjects]

        if len(subject_keys) != len(set(subject_keys)):
            raise ValueError("Subjects must be unique")

        factor_keys = [name.casefold() for name in self.factors]

        if len(factor_keys) != len(set(factor_keys)):
            raise ValueError("Factors must be unique")

        if self.mode in {"compare", "rank"} and len(self.subjects) < 2:
            raise ValueError(
                "Comparison or ranking requires at least two subjects"
            )

        return self

class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: NonEmptyText
    question: NonEmptyText
    reason: NonEmptyText

class ClarificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[ClarificationQuestion] = Field(
        default_factory=list
    )

    @property
    def needs_clarification(self) -> bool:
        return bool(self.questions)


class SourceRecord(BaseModel):
    """Describe material retrieved by a tool or loaded from a dataset."""

    model_config = ConfigDict(extra="forbid")

    # Created by our retrieval code, not invented by the LLM.
    source_id: NonEmptyText
    title: NonEmptyText

    # The source type determines which location field is required.
    kind: Literal["web", "dataset"]
    url: HttpUrl | None = None
    dataset_ref: NonEmptyText | None = None

    # Unknown publication dates stay unknown.
    published_on: date | None = None

    # Explicit timestamp supplied when the material is retrieved.
    retrieved_at: AwareDatetime

    # Keeps synthetic examples distinguishable from real research.
    is_test_data: bool = False

    @model_validator(mode="after")
    def validate_location(self):
        """Require the correct location for the selected source type."""

        if self.kind == "web":
            if self.url is None or self.dataset_ref is not None:
                raise ValueError(
                    "Web sources require a URL and no dataset_ref"
                )

        if self.kind == "dataset":
            if self.dataset_ref is None or self.url is not None:
                raise ValueError(
                    "Dataset sources require dataset_ref and no URL"
                )

        return self


class EvidenceItem(BaseModel):
    """Store an extracted passage or dataset row for later verification."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: NonEmptyText

    # Acts like a foreign key to SourceRecord.source_id.
    source_id: NonEmptyText

    # These remain general: a player, product, platform, or another subject.
    subject: NonEmptyText
    factor: NonEmptyText

    # Preserve the retrieved text or a faithful representation of a row.
    # This is evidence material, not the model's interpretation.
    excerpt: NonEmptyText

    # Examples: "Table 2, row 7", "page 4", or a section heading.
    locator: NonEmptyText

    # Preserve contextual limits so incompatible statistics aren't mixed.
    time_period: NonEmptyText | None = None
    coverage: NonEmptyText | None = None


class ResearchFinding(BaseModel):
    """Represent a sourced claim awaiting independent verification."""

    model_config = ConfigDict(extra="forbid")

    finding_id: NonEmptyText
    subject: NonEmptyText
    factor: NonEmptyText
    claim: NonEmptyText

    # Distinguish a reported observation from an interpretation.
    claim_type: Literal["reported_fact", "interpretation"]

    # A finding must reference at least one evidence item.
    evidence_ids: list[NonEmptyText] = Field(min_length=1)

    # Record qualifications rather than hiding them in the final report.
    limitations: list[NonEmptyText] = Field(default_factory=list)

    # This stage cannot mark its own findings as verified.
    verification_status: Literal["unverified"] = "unverified"


class ResearchBundle(BaseModel):
    """Group research artifacts and check their reference integrity."""

    model_config = ConfigDict(extra="forbid")

    sources: list[SourceRecord] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    findings: list[ResearchFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        """Reject duplicate IDs and references to missing records."""

        source_ids = [item.source_id for item in self.sources]
        evidence_ids = [item.evidence_id for item in self.evidence]
        finding_ids = [item.finding_id for item in self.findings]

        # Duplicate IDs would make citation resolution ambiguous.
        for label, identifiers in (
            ("source", source_ids),
            ("evidence", evidence_ids),
            ("finding", finding_ids),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"Duplicate {label} IDs")

        known_sources = set(source_ids)
        known_evidence = set(evidence_ids)

        # Every evidence item must point to an existing source.
        for item in self.evidence:
            if item.source_id not in known_sources:
                raise ValueError(
                    f"Evidence {item.evidence_id} references "
                    f"unknown source {item.source_id}"
                )

        # Every finding must point to existing, distinct evidence items.
        for finding in self.findings:
            if len(finding.evidence_ids) != len(set(finding.evidence_ids)):
                raise ValueError(
                    f"Finding {finding.finding_id} repeats evidence IDs"
                )

            missing = set(finding.evidence_ids) - known_evidence

            if missing:
                raise ValueError(
                    f"Finding {finding.finding_id} references "
                    f"unknown evidence: {sorted(missing)}"
                )

        return self

class ComparisonRow(BaseModel):
    """One result for a subject and factor, linked to its evidence."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    subject: NonEmptyText
    factor: NonEmptyText

    # Support numerical results and descriptive results.
    # Examples: 0.65 goals per 90 minutes, or "ISO 27001".
    value: float | NonEmptyText
    unit: NonEmptyText | None = None

    # These reference EvidenceItem.evidence_id, not source IDs.
    evidence_ids: list[NonEmptyText] = Field(min_length=1)


class RankingEntry(BaseModel):
    """A subject's position and score under the chosen ranking method."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    # Equal positions are permitted so ties can be represented.
    position: int = Field(ge=1)
    subject: NonEmptyText

    # Keep the score scale flexible; the ranking method defines it.
    score: float
    evidence_ids: list[NonEmptyText] = Field(min_length=1)


class FinalReport(BaseModel):
    """The shared output contract for Aegis research architectures."""

    model_config = ConfigDict(extra="forbid")

    summary: NonEmptyText
    mode: Literal["research", "compare", "rank"]
    subjects: list[NonEmptyText] = Field(min_length=1, max_length=5)

    comparison_rows: list[ComparisonRow] = Field(default_factory=list)
    ranking: list[RankingEntry] = Field(default_factory=list)
    findings: list[ResearchFinding] = Field(default_factory=list)
    limitations: list[NonEmptyText] = Field(default_factory=list)

    # The report's bibliography references SourceRecord.source_id.
    # Rows and findings reference the more specific evidence IDs.
    citations: list[NonEmptyText] = Field(default_factory=list)

    # "Completed" describes report production, not factual verification.
    # "Degraded" means a report was produced with limitations.
    status: Literal["completed", "degraded"]

    @model_validator(mode="after")
    def validate_report_structure(self):
        """Check rules that can be evaluated without external evidence."""

        subject_keys = [subject.casefold() for subject in self.subjects]
        known_subjects = set(subject_keys)

        if len(subject_keys) != len(known_subjects):
            raise ValueError("Report subjects must be unique")

        if self.mode in {"compare", "rank"} and len(self.subjects) < 2:
            raise ValueError(
                "Comparison or ranking requires at least two subjects"
            )

        # Research and comparison reports must not silently introduce
        # a ranking that the user did not request.
        if self.mode == "rank" and not self.ranking:
            raise ValueError("Rank mode requires a ranking")

        if self.mode != "rank" and self.ranking:
            raise ValueError("Ranking is only allowed in rank mode")

        # Every structured result must concern a declared subject.
        results = [
            *self.comparison_rows,
            *self.ranking,
            *self.findings,
        ]

        for result in results:
            if result.subject.casefold() not in known_subjects:
                raise ValueError(
                    f"Unknown report subject: {result.subject}"
                )

            if len(result.evidence_ids) != len(set(result.evidence_ids)):
                raise ValueError("Repeated evidence IDs in report result")

        # A subject should appear at most once in a ranking.
        ranked_subjects = [
            entry.subject.casefold() for entry in self.ranking
        ]

        if len(ranked_subjects) != len(set(ranked_subjects)):
            raise ValueError("Ranking subjects must be unique")

        # A completed ranking must account for every requested subject.
        # A degraded report may rank a subset and explain the omissions.
        if (
            self.mode == "rank"
            and self.status == "completed"
            and set(ranked_subjects) != known_subjects
        ):
            raise ValueError(
                "Completed ranking must include every report subject"
            )

        if len(self.citations) != len(set(self.citations)):
            raise ValueError("Report citations must be unique")

        if self.status == "degraded" and not self.limitations:
            raise ValueError("Degraded reports must explain limitations")

        return self

def validate_report_against_bundle(
    report: FinalReport,
    bundle: ResearchBundle,
) -> FinalReport:
    """Validate report references against the collected research artifacts.

    This checks reference integrity. It does not establish whether a
    source is truthful or whether its text supports a particular claim.
    """

    # Revalidate snapshots because model fields may have been modified
    # after their initial construction.
    report = FinalReport.model_validate(report.model_dump())
    bundle = ResearchBundle.model_validate(bundle.model_dump())

    known_sources = {
        source.source_id for source in bundle.sources
    }
    evidence_by_id = {
        item.evidence_id: item for item in bundle.evidence
    }

    # Bibliography entries must resolve to collected sources.
    unknown_sources = set(report.citations) - known_sources

    if unknown_sources:
        raise ValueError(
            f"Report cites unknown sources: {sorted(unknown_sources)}"
        )

    # Collect evidence references from every structured report section.
    referenced_evidence = {
        evidence_id
        for result in [
            *report.comparison_rows,
            *report.ranking,
            *report.findings,
        ]
        for evidence_id in result.evidence_ids
    }

    unknown_evidence = referenced_evidence - set(evidence_by_id)

    if unknown_evidence:
        raise ValueError(
            f"Report cites unknown evidence: {sorted(unknown_evidence)}"
        )

    # Every referenced evidence item's source must also appear
    # in the report's bibliography.
    required_sources = {
        evidence_by_id[evidence_id].source_id
        for evidence_id in referenced_evidence
    }
    missing_citations = required_sources - set(report.citations)

    if missing_citations:
        raise ValueError(
            "Report bibliography is missing sources: "
            f"{sorted(missing_citations)}"
        )

    return report


class PlanStep(BaseModel):
    """One task assigned to a worker, with explicit prerequisites."""

    model_config = ConfigDict(extra="forbid")

    step_id: NonEmptyText
    worker: Literal["evidence", "web", "analysis"]
    subject: NonEmptyText
    factor: NonEmptyText

    # These are task IDs, not evidence IDs.
    # An empty list means the task has no prerequisites.
    depends_on: list[NonEmptyText] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    """A collection of tasks with a valid dependency structure."""

    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep] = Field(min_length=1, max_length=150)
    rationale: NonEmptyText

    @model_validator(mode="after")
    def validate_dependencies(self):
        """Reject ambiguous IDs, broken dependencies and cycles."""

        step_ids = [step.step_id for step in self.steps]

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Plan step IDs must be unique")

        steps_by_id = {
            step.step_id: step
            for step in self.steps
        }

        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                raise ValueError(
                    f"Step {step.step_id} repeats dependencies"
                )

            if step.step_id in step.depends_on:
                raise ValueError(
                    f"Step {step.step_id} depends on itself"
                )

            unknown = set(step.depends_on) - set(steps_by_id)

            if unknown:
                raise ValueError(
                    f"Step {step.step_id} has unknown dependencies: "
                    f"{sorted(unknown)}"
                )

        # A cycle would make tasks wait on one another forever.
        # Example: task A requires B, while B requires A.
        dependency_graph = {
            step.step_id: set(step.depends_on)
            for step in self.steps
        }

        try:
            tuple(TopologicalSorter(dependency_graph).static_order())
        except CycleError:
            raise ValueError("Plan contains a dependency cycle") from None

        for step in self.steps:
            if step.worker != "analysis":
                continue

            # For this first planner, analysis must directly depend
            # on retrieval for the same subject and factor.
            # Either a dataset worker or a web worker can supply it.
            has_matching_evidence = any(
                steps_by_id[dependency].worker in {"evidence", "web"}
                and steps_by_id[dependency].subject.casefold()
                == step.subject.casefold()
                and steps_by_id[dependency].factor.casefold()
                == step.factor.casefold()
                for dependency in step.depends_on
            )

            if not has_matching_evidence:
                raise ValueError(
                    f"Analysis step {step.step_id} requires matching "
                    "evidence or web dependency"
                )

        return self

def validate_plan_against_request(
    plan: ResearchPlan,
    request: ResearchRequest,
) -> ResearchPlan:
    """Require retrieval coverage for every requested subject/factor."""

    # Revalidate snapshots in case objects changed after construction.
    plan = ResearchPlan.model_validate(plan.model_dump())
    request = ResearchRequest.model_validate(request.model_dump())

    if not request.factors:
        raise ValueError("Clarify research factors before planning")

    # Cartesian product: every subject paired with every factor.
    expected_pairs = {
        (subject.casefold(), factor.casefold())
        for subject in request.subjects
        for factor in request.factors
    }

    all_pairs = {
        (step.subject.casefold(), step.factor.casefold())
        for step in plan.steps
    }

    # A planner must not silently expand the user's research scope.
    unexpected = all_pairs - expected_pairs

    if unexpected:
        raise ValueError(
            f"Plan contains unrequested subject/factor pairs: "
            f"{sorted(unexpected)}"
        )

    retrieval_pairs = {
        (step.subject.casefold(), step.factor.casefold())
        for step in plan.steps
        if step.worker in {"evidence", "web"}
    }

    # An analysis task alone does not count as evidence collection.
    missing = expected_pairs - retrieval_pairs

    if missing:
        raise ValueError(
            f"Plan is missing evidence collection for: {sorted(missing)}"
        )

    return plan