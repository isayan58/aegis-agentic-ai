"""LangChain wrappers around the tested local functions."""

from typing import Literal

from langchain_core.tools import tool

from aegis.tools import calculators as calc
from aegis.tools.evidence import load_fixture, lookup_evidence


@tool
def load_fixture_tool(dataset_ref: str) -> dict:
    """Load a fictional fixture: football_demo_v1 or platforms_demo_v1."""

    return load_fixture(dataset_ref).model_dump(mode="json")


@tool
def lookup_evidence_tool(
    subject: str,
    factor: str,
    dataset_ref: str,
) -> dict:
    """Look up fictional evidence; return a reason when data is unavailable.

    Football factors: scoring, creativity, availability.
    Platform factors: operating cost, security, reliability, coverage.
    """

    return lookup_evidence(
        subject=subject,
        factor=factor,
        dataset_ref=dataset_ref,
    ).model_dump(mode="json")


@tool
def per_90_tool(value: float, minutes: float) -> float:
    """Calculate events per 90 minutes; minutes must be positive."""

    return calc.per_90(value, minutes)


@tool
def normalize_tool(
    values: dict[str, float],
    direction: Literal["higher", "lower"],
) -> dict[str, float]:
    """Normalize comparable values to 0–1; equal values receive 0.5."""

    return calc.normalize(values, direction)


@tool
def weighted_score_tool(
    scores: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Combine normalized factor scores using weights that sum to one."""

    return calc.weighted_score(scores, weights)


@tool
def rank_tool(scores: dict[str, float]) -> list[dict]:
    """Rank subjects by descending score, preserving exact ties."""

    return calc.rank(scores)


@tool
def sensitivity_check_tool(
    scores: dict[str, dict[str, float]],
    weights: dict[str, float],
) -> dict:
    """Check whether relative ±10% weight changes alter the winner set."""

    return calc.sensitivity_check(scores, weights)


@tool
def calculator_tool(expression: str) -> float:
    """Calculate numbers with +, -, *, / and parentheses only."""

    return calc.calculator(expression)


TOOLS = [
    load_fixture_tool,
    lookup_evidence_tool,
    per_90_tool,
    normalize_tool,
    weighted_score_tool,
    rank_tool,
    sensitivity_check_tool,
    calculator_tool,
]