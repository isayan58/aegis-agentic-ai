"""Contracts for the first deterministic evaluation dataset."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aegis.schemas import NonEmptyText


class EvalModel(BaseModel):
    """Catch misspelled fields and non-finite numeric expectations."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )


class ToolCall(EvalModel):
    """An explicit calculation to run as part of a valid case."""

    # Keep dispatch limited to the tools evaluated in this dataset.
    name: Literal["per_90", "weighted_score", "calculator"]
    arguments: dict[str, Any]


class EvalInput(EvalModel):
    """Raw application inputs, including intentionally invalid ones."""

    # Do not type these as ResearchRequest or ResearchBundle here.
    # Invalid payloads must survive dataset loading so we can test rejection.
    request: dict[str, Any] | None = None
    bundle: dict[str, Any] | None = None

    tools: list[ToolCall] = Field(default_factory=list)
    # Identifies the local evidence adapter for live baseline evaluations.
    dataset_ref: NonEmptyText | None = None


class Expected(EvalModel):
    """The behavior a case must produce to pass."""

    outcome: Literal["accepted", "clarification", "rejected"]

    clarification_fields: list[NonEmptyText] = Field(
        default_factory=list
    )

    # Match a particular validation failure, not just any exception.
    error_type: NonEmptyText | None = None
    error_contains: NonEmptyText | None = None

    # Numeric results correspond to input.tools in the same order.
    tool_outputs: list[float] = Field(default_factory=list)
        # Each entry is (worker, subject, factor).
    # These expectations are never passed to the agent.
    workers: list[tuple[str, str, str]] = Field(default_factory=list)

    # Expected research/calculation calls, excluding FinalReport submission.
    tool_sequence: list[NonEmptyText] = Field(default_factory=list)


class EvalCase(EvalModel):
    """One versioned evaluation example."""

    id: NonEmptyText
    category: Literal["valid", "clarification", "invalid", "reference"]

    input: EvalInput
    expected: Expected

    @model_validator(mode="after")
    def validate_case_contract(self):
        """Reject inconsistent evaluation definitions."""

        required_outcome = {
            "valid": "accepted",
            "clarification": "clarification",
            "invalid": "rejected",
            "reference": "rejected",
        }

        if self.expected.outcome != required_outcome[self.category]:
            raise ValueError("Category does not match expected outcome")

        # Reference cases test bundles; all other cases test requests.
        if self.category == "reference":
            if self.input.bundle is None or self.input.request is not None:
                raise ValueError("Reference cases require only a bundle")
        else:
            if self.input.request is None or self.input.bundle is not None:
                raise ValueError("Request cases require only a request")

        fields = self.expected.clarification_fields

        if len(fields) != len(set(fields)):
            raise ValueError("Duplicate expected clarification fields")

        if self.category == "clarification":
            if not fields:
                raise ValueError("Clarification cases need expected fields")
        elif fields:
            raise ValueError("Only clarification cases may expect questions")

        if self.expected.outcome == "rejected":
            if not (
                self.expected.error_type
                and self.expected.error_contains
            ):
                raise ValueError(
                    "Rejection cases require an error type and message"
                )
        elif (
            self.expected.error_type is not None
            or self.expected.error_contains is not None
        ):
            raise ValueError("Non-rejection cases cannot expect errors")

        if self.input.tools and self.category != "valid":
            raise ValueError("Only valid cases run calculation checks")

        if len(self.input.tools) != len(self.expected.tool_outputs):
            raise ValueError("Every tool call needs an expected output")

        return self