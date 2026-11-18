"""Verify token-cost arithmetic against the configured price table."""

from decimal import Decimal

import pytest

from aegis.llm.pricing import (
    UnknownModelPriceError,
    calculate_cost,
    get_price,
)


@pytest.fixture
def usage():
    """Provide fresh synthetic usage for every test."""

    return {
        "provider": "openai",
        "requested_model": "gpt-5.4",
        "input_tokens": 1000,
        "cached_input_tokens": 0,
        "output_tokens": 500,
        "reasoning_tokens": 0,
    }


def test_million_input_and_output_tokens(usage):
    """Check the reference calculation specified in issue #9."""

    usage["input_tokens"] = 1_000_000
    usage["output_tokens"] = 1_000_000

    assert calculate_cost(usage) == Decimal("17.50")


def test_small_call_cost(usage):
    """Small charges should preserve exact decimal arithmetic."""

    result = calculate_cost(usage)

    assert isinstance(result, Decimal)
    assert result == Decimal("0.0100")


def test_cached_input_uses_cached_rate(usage):
    """Cached tokens must not also be billed as uncached input."""

    usage["cached_input_tokens"] = 500

    assert calculate_cost(usage) == Decimal("0.008875")


def test_reasoning_tokens_are_not_added_twice(usage):
    """Reasoning is a breakdown of output, not an additional total."""

    before = calculate_cost(usage)

    usage["reasoning_tokens"] = 200

    assert calculate_cost(usage) == before


def test_cached_count_is_capped_at_total_input(usage):
    """Apply the current policy for inconsistent cache counts."""

    usage["cached_input_tokens"] = 1500

    # Only the actual 1,000 input tokens can receive the cached rate.
    # 1000 × $0.25 / 1M + 500 × $15.00 / 1M = $0.00775
    assert calculate_cost(usage) == Decimal("0.00775")


def test_unknown_model_price_raises():
    """Missing prices must never silently become a zero-dollar cost."""

    with pytest.raises(UnknownModelPriceError):
        get_price("unconfigured-model")


def test_cost_calculation_rejects_unknown_model(usage):
    """The calculation path must also fail when pricing is unavailable."""

    usage["requested_model"] = "unconfigured-model"

    with pytest.raises(UnknownModelPriceError):
        calculate_cost(usage)


@pytest.mark.parametrize(
    "field",
    [
        "input_tokens",
        "output_tokens",
        "cached_input_tokens",
    ],
)
@pytest.mark.parametrize(
    "bad_value",
    [-1, 10.9, True, "100"],
)
def test_invalid_token_counts_are_rejected(usage, field, bad_value):
    """Malformed usage must never silently become a monetary value."""

    usage[field] = bad_value

    with pytest.raises(
        ValueError,
        match=f"{field} must be a non-negative integer",
    ):
        calculate_cost(usage)


@pytest.mark.parametrize(
    "field",
    ["input_tokens", "output_tokens"],
)
def test_required_token_counts_cannot_be_missing(usage, field):
    """Unknown usage must not be interpreted as zero usage."""

    usage.pop(field)

    with pytest.raises(KeyError) as exc_info:
        calculate_cost(usage)

    assert exc_info.value.args[0] == field


def test_explicit_zero_usage_is_valid(usage):
    """An explicitly reported zero remains a legitimate value."""

    usage["input_tokens"] = 0
    usage["cached_input_tokens"] = 0
    usage["output_tokens"] = 0

    assert calculate_cost(usage) == Decimal("0")