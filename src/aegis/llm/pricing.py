"""
Converts token usage into a USD cost.

Prices are per 1M tokens and must be checked against the provider's pricing
page whenever a model is added or changed. An unknown model raises instead of
costing $0, for the same reason missing usage raises in usage.py: a silent
zero would let spending escape the budget.

Money is calculated with Decimal so repeated small costs do not accumulate
floating-point error.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    input_per_1m: Decimal
    cached_input_per_1m: Decimal
    output_per_1m: Decimal


# Keyed by the requested model name. For Azure this is the deployment name,
# so keep deployment names equal to the model name or add an entry here.
# Source: OpenAI API pricing page, checked 2026-11-17.
PRICES: dict[str, ModelPrice] = {
    "gpt-5.4": ModelPrice(
        input_per_1m=Decimal("2.50"),
        cached_input_per_1m=Decimal("0.25"),
        output_per_1m=Decimal("15.00"),
    ),
    "gpt-5-mini": ModelPrice(
        input_per_1m=Decimal("0.25"),
        cached_input_per_1m=Decimal("0.025"),
        output_per_1m=Decimal("2.00"),
    ),
}


class UnknownModelPriceError(KeyError):
    """Raised when no price is configured for a model."""


def get_price(model: str) -> ModelPrice:
    try:
        return PRICES[model]
    except KeyError:
        raise UnknownModelPriceError(
            f"No price configured for model '{model}'. Add it to PRICES."
        ) from None


def calculate_cost(usage: Mapping[str, Any]) -> Decimal:
    """Calculate USD token cost using the configured model rates."""

    # A missing or unknown model must fail instead of costing zero.
    price = get_price(usage["requested_model"])

    # Input and output counts are required.
    # Missing fields raise KeyError rather than defaulting to zero.
    input_tokens = _validate_token_count(
        usage["input_tokens"],
        "input_tokens",
    )

    output_tokens = _validate_token_count(
        usage["output_tokens"],
        "output_tokens",
    )

    # Cached usage is optional in our normalized usage contract.
    reported_cached_tokens = _validate_token_count(
        usage.get("cached_input_tokens", 0),
        "cached_input_tokens",
    )

    # Preserve our existing policy: cached input cannot exceed input.
    cached_tokens = min(reported_cached_tokens, input_tokens)
    uncached_tokens = input_tokens - cached_tokens

    # Reasoning tokens are already included in output_tokens.
    # total_tokens is also not an additional billable category.
    return (
        uncached_tokens * price.input_per_1m
        + cached_tokens * price.cached_input_per_1m
        + output_tokens * price.output_per_1m
    ) / PER_MILLION

def _validate_token_count(value: Any, field: str) -> int:
    """Require a non-negative integer without silently converting values."""

    # bool is a subclass of int, so use an exact type check.
    # This rejects True, floats, numeric strings, and None.
    if type(value) is not int or value < 0:
        raise ValueError(
            f"{field} must be a non-negative integer"
        )

    return value