"""Rules for combining updates to shared graph state."""

from decimal import Decimal
from typing import TypedDict, TypeVar


T = TypeVar("T")


def merge_by_id(
    current: dict[str, T],
    update: dict[str, T],
) -> dict[str, T]:
    """Merge records without modifying either input dictionary."""

    # A later update replaces the complete record at a matching ID.
    return {**current, **update}


def append(
    current: list[T],
    update: list[T],
) -> list[T]:
    """Preserve existing entries and append new entries."""

    # Create a new list rather than mutating the existing state.
    return [*current, *update]


class UsageTotals(TypedDict):
    """Accounting values for one provider/model combination."""

    tokens_in: int
    tokens_out: int
    cost_usd: Decimal


def validate_usage(value: UsageTotals) -> None:
    """Reject invalid accounting values before accumulating them."""

    required_fields = {"tokens_in", "tokens_out", "cost_usd"}

    if set(value) != required_fields:
        raise ValueError(
            "Usage requires tokens_in, tokens_out, and cost_usd"
        )

    for field in ("tokens_in", "tokens_out"):
        # Exact type checking also rejects True/False as token counts.
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError(
                f"{field} must be a non-negative integer"
            )

    cost = value["cost_usd"]

    if (
        not isinstance(cost, Decimal)
        or not cost.is_finite()
        or cost < 0
    ):
        raise ValueError(
            "cost_usd must be a finite non-negative Decimal"
        )


def sum_usage(
    current: dict[str, UsageTotals],
    update: dict[str, UsageTotals],
) -> dict[str, UsageTotals]:
    """Add usage deltas separately for each provider/model."""

    result: dict[str, UsageTotals] = {}

    # Process both inputs into fresh dictionaries.
    # Neither input is modified.
    for batch in (current, update):
        for model_key, delta in batch.items():
            if not isinstance(model_key, str) or not model_key.strip():
                raise ValueError(
                    "Usage requires a non-empty provider/model key"
                )

            validate_usage(delta)

            previous = result.get(
                model_key,
                {
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cost_usd": Decimal("0"),
                },
            )

            result[model_key] = {
                "tokens_in": (
                    previous["tokens_in"] + delta["tokens_in"]
                ),
                "tokens_out": (
                    previous["tokens_out"] + delta["tokens_out"]
                ),
                "cost_usd": (
                    previous["cost_usd"] + delta["cost_usd"]
                ),
            }

    return result