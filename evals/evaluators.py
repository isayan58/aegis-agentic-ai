"""Metrics for planner routing and agent tool selection."""

from collections import Counter


def routing_matches(expected, actual) -> bool:
    """Compare worker assignments, preserving duplicate-task mistakes."""

    def normalize(items):
        return Counter(
            (worker, subject.casefold(), factor.casefold())
            for worker, subject, factor in items
        )

    return normalize(expected) == normalize(actual)


def tool_metrics(expected: list[str], actual: list[str]) -> dict:
    """Score tool names and counts, with sequence as a separate metric.

    Counter intersection counts matched occurrences.
    Repeating a tool unnecessarily reduces precision.
    Omitting a required call reduces recall.
    """

    wanted = Counter(expected)
    observed = Counter(actual)

    matched = sum((wanted & observed).values())

    # Explicit conventions for empty sequences.
    precision = (
        matched / len(actual)
        if actual
        else (1.0 if not expected else 0.0)
    )
    recall = matched / len(expected) if expected else 1.0

    return {
        "precision": precision,
        "recall": recall,
        "sequence_exact": expected == actual,
        "expected_calls": len(expected),
        "actual_calls": len(actual),
        "matched_calls": matched,
    }