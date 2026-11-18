from concurrent.futures import ThreadPoolExecutor
import logging
import threading
from decimal import Decimal

import pytest

from aegis.config import Settings
from aegis.llm.budget import BudgetExceededError, BudgetTracker
from aegis.llm.pricing import UnknownModelPriceError, calculate_cost


def make_usage(
    model="gpt-5-mini",
    input_tokens=0,
    output_tokens=0,
    cached_input_tokens=0,
    reasoning_tokens=0,
    provider="azure",
):
    return {
        "provider": provider,
        "requested_model": model,
        "reported_model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
    }


# --- pricing ---------------------------------------------------------------


def test_cost_for_known_token_counts():
    # gpt-5.4: 1M input at $2.50 + 1M output at $15.00
    usage = make_usage("gpt-5.4", input_tokens=1_000_000, output_tokens=1_000_000)

    assert calculate_cost(usage) == Decimal("17.50")


def test_cost_for_small_call_is_exact():
    # gpt-5-mini: 1,000 input ($0.00025) + 500 output ($0.001)
    usage = make_usage("gpt-5-mini", input_tokens=1_000, output_tokens=500)

    assert calculate_cost(usage) == Decimal("0.00125")


def test_cached_input_billed_at_cached_rate():
    # 1M input of which 400k cached:
    # 600k x $2.50 + 400k x $0.25 = $1.50 + $0.10
    usage = make_usage(
        "gpt-5.4", input_tokens=1_000_000, cached_input_tokens=400_000
    )

    assert calculate_cost(usage) == Decimal("1.60")


def test_reasoning_tokens_not_double_counted():
    # Reasoning tokens are part of output tokens already.
    with_reasoning = make_usage(
        "gpt-5-mini", output_tokens=1_000, reasoning_tokens=800
    )
    without_reasoning = make_usage("gpt-5-mini", output_tokens=1_000)

    assert calculate_cost(with_reasoning) == calculate_cost(without_reasoning)


def test_unknown_model_raises_instead_of_costing_zero():
    usage = make_usage("not-a-real-model", input_tokens=10, output_tokens=10)

    with pytest.raises(UnknownModelPriceError, match="not-a-real-model"):
        calculate_cost(usage)


# --- budget ----------------------------------------------------------------


def test_tracker_accumulates_spend_and_records_calls():
    tracker = BudgetTracker("1.00")

    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000, output_tokens=500))
    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000, output_tokens=500))

    assert tracker.spent_usd == Decimal("0.0025")
    assert tracker.remaining_usd == Decimal("0.9975")
    assert len(tracker.calls) == 2
    assert tracker.calls[0].cost_usd == Decimal("0.00125")


def test_check_allows_calls_under_the_cap():
    tracker = BudgetTracker("1.00")
    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000))

    tracker.check()  # does not raise


def test_call_after_cap_is_blocked():
    tracker = BudgetTracker("0.01")

    tracker.check()
    # 1M gpt-5-mini input tokens cost $0.25, well over the $0.01 cap
    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000_000))

    with pytest.raises(BudgetExceededError):
        tracker.check()


def test_reaching_cap_exactly_blocks_next_call():
    tracker = BudgetTracker("0.25")
    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000_000))  # $0.25

    with pytest.raises(BudgetExceededError):
        tracker.check()


def test_remaining_never_negative():
    tracker = BudgetTracker("0.01")
    tracker.record(make_usage("gpt-5-mini", input_tokens=1_000_000))

    assert tracker.remaining_usd == Decimal(0)


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_non_positive_limit_rejected(limit):
    with pytest.raises(ValueError):
        BudgetTracker(limit)


def test_concurrent_records_are_not_lost():
    """Eight workers must record all 400 calls without losing updates."""

    tracker = BudgetTracker("100")

    usage = make_usage(
        "gpt-5-mini",
        input_tokens=1_000,
        output_tokens=500,
    )

    def record_batch():
        # Each worker records 50 completed calls.
        for _ in range(50):
            tracker.record(usage)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(record_batch)
            for _ in range(8)
        ]

        # Calling result() propagates worker exceptions into the test.
        for future in futures:
            future.result()

    assert len(tracker.calls) == 400
    assert tracker.spent_usd == Decimal("0.00125") * 400


def test_log_contains_metadata_only(caplog):
    tracker = BudgetTracker("1.00")
    usage = make_usage("gpt-5-mini", input_tokens=1_000, output_tokens=500)
    usage["prompt"] = "SECRET-PROMPT-TEXT"

    with caplog.at_level(logging.INFO, logger="aegis.llm.budget"):
        tracker.record(usage)

    assert "model=gpt-5-mini" in caplog.text
    assert "cost_usd=0.001250" in caplog.text
    assert "SECRET-PROMPT-TEXT" not in caplog.text


# --- settings --------------------------------------------------------------


def _settings(**overrides):
    values = dict(
        _env_file=None,
        openai_api_key="fake-openai-key",
        azure_openai_api_key="fake-azure-key",
        azure_openai_base_url="https://example.openai.azure.com/openai/v1/",
        azure_openai_deployment="gpt-5-mini",
    )
    values.update(overrides)
    return Settings(**values)


def test_budget_limit_defaults_and_overrides(monkeypatch):
    """Test the default without interference from the shell environment."""

    monkeypatch.delenv("BUDGET_LIMIT_USD", raising=False)

    assert _settings().budget_limit_usd == Decimal("1.00")

    assert _settings(
        budget_limit_usd="0.50"
    ).budget_limit_usd == Decimal("0.50")


def test_budget_limit_must_be_positive():
    with pytest.raises(ValueError):
        _settings(budget_limit_usd="0")

@pytest.mark.parametrize(
    "limit",
    ["NaN", "Infinity", "-Infinity", "not-a-number"],
)
def test_invalid_budget_limits_are_rejected(limit):
    """The cutoff must always be a finite positive amount."""

    with pytest.raises(ValueError, match="finite positive"):
        BudgetTracker(limit)


def test_failed_cost_calculation_does_not_change_tracker():
    """An unpriced call must fail loudly without corrupting totals."""

    tracker = BudgetTracker("1.00")

    with pytest.raises(UnknownModelPriceError):
        tracker.record(
            make_usage("unconfigured-model", input_tokens=100)
        )

    assert tracker.spent_usd == Decimal("0")
    assert tracker.remaining_usd == Decimal("1.00")
    assert tracker.calls == ()


def test_budget_exhaustion_emits_warning(caplog):
    """Reaching the cutoff should be observable in logs."""

    tracker = BudgetTracker("0.25")

    with caplog.at_level(
        logging.WARNING,
        logger="aegis.llm.budget",
    ):
        tracker.record(
            make_usage("gpt-5-mini", input_tokens=1_000_000)
        )

    assert "budget_exhausted" in caplog.text


def test_extra_sensitive_fields_are_not_logged(caplog):
    """Only selected accounting fields should reach the logs."""

    tracker = BudgetTracker("1.00")

    usage = make_usage(
        "gpt-5-mini",
        input_tokens=100,
        output_tokens=20,
    )

    # These extra fields must never be copied wholesale into logs.
    usage["prompt"] = "PRIVATE-PROMPT-SENTINEL"
    usage["api_key"] = "PRIVATE-KEY-SENTINEL"
    usage["response"] = "PRIVATE-RESPONSE-SENTINEL"

    with caplog.at_level(
        logging.INFO,
        logger="aegis.llm.budget",
    ):
        tracker.record(usage)

    assert "llm_call" in caplog.text
    assert "PRIVATE-PROMPT-SENTINEL" not in caplog.text
    assert "PRIVATE-KEY-SENTINEL" not in caplog.text
    assert "PRIVATE-RESPONSE-SENTINEL" not in caplog.text


def test_completed_inflight_calls_are_recorded_after_exhaustion():
    """Already incurred costs must be recorded even after the cutoff."""

    tracker = BudgetTracker("0.001")

    usage = make_usage(
        "gpt-5-mini",
        input_tokens=1_000,
        output_tokens=500,
    )

    # Simulate two calls that started before either one finished.
    tracker.check()
    tracker.check()

    tracker.record(usage)
    tracker.record(usage)

    assert len(tracker.calls) == 2
    assert tracker.spent_usd == Decimal("0.00250")
    assert tracker.remaining_usd == Decimal("0")

    # A subsequent call must now be blocked.
    with pytest.raises(BudgetExceededError):
        tracker.check()

@pytest.mark.parametrize("limit", ["NaN", "Infinity", "-Infinity"])
def test_settings_reject_non_finite_budget(limit):
    with pytest.raises(ValueError):
        _settings(budget_limit_usd=limit)