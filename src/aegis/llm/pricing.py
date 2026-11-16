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
    """
    Cost in USD for one call, from the dict returned by extract_usage().

    Cached input tokens are a subset of input tokens and are billed at the
    cached rate. Reasoning tokens are already included in output tokens, so
    they are not added again.
    """
    price = get_price(usage["requested_model"])

    input_tokens = int(usage["input_tokens"])
    output_tokens = int(usage["output_tokens"])
    cached_tokens = min(int(usage.get("cached_input_tokens", 0)), input_tokens)
    uncached_tokens = input_tokens - cached_tokens

    cost = (
        uncached_tokens * price.input_per_1m
        + cached_tokens * price.cached_input_per_1m
        + output_tokens * price.output_per_1m
    ) / PER_MILLION

    return cost
