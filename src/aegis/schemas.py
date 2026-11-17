"""Validated data structures shared across the Aegis application."""

from datetime import date
from typing import Annotated, Literal

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