"""
Tracks spending for one run and blocks calls once the cap is reached.

Usage around every model call:

    tracker.check()                 # before: raises if the cap is reached
    response = model.invoke(...)
    tracker.record(extract_usage(response, ...))   # after: adds the cost

check() cannot know what the next call will cost, so the final call of a run
can take spending slightly past the cap. The cap stops further calls; it does
not guarantee an exact ceiling. Keep the cap a little below what you can
afford to lose.

The tracker is thread-safe, because parallel graph branches will share it.
Only metadata is logged: never prompts, responses or keys.
"""

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from aegis.llm.pricing import calculate_cost

logger = logging.getLogger(__name__)


class BudgetExceededError(RuntimeError):
    """Raised when a call is attempted after the budget is used up."""


@dataclass(frozen=True)
class CallRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    cost_usd: Decimal


class BudgetTracker:
    def __init__(self, limit_usd: Decimal | str | int) -> None:
        limit = Decimal(str(limit_usd))
        if limit <= 0:
            raise ValueError("Budget limit must be greater than zero")

        self._limit = limit
        self._spent = Decimal(0)
        self._calls: list[CallRecord] = []
        self._lock = threading.Lock()

    @property
    def limit_usd(self) -> Decimal:
        return self._limit

    @property
    def spent_usd(self) -> Decimal:
        with self._lock:
            return self._spent

    @property
    def remaining_usd(self) -> Decimal:
        with self._lock:
            return max(self._limit - self._spent, Decimal(0))

    @property
    def calls(self) -> tuple[CallRecord, ...]:
        with self._lock:
            return tuple(self._calls)

    def check(self) -> None:
        """Call before every model call."""
        with self._lock:
            if self._spent >= self._limit:
                raise BudgetExceededError(
                    f"Budget of ${self._limit} used up "
                    f"(spent ${self._spent:.6f}); call blocked."
                )

    def record(self, usage: Mapping[str, Any]) -> CallRecord:
        """Call after every model call, with the dict from extract_usage()."""
        cost = calculate_cost(usage)

        call = CallRecord(
            provider=usage["provider"],
            model=usage["requested_model"],
            input_tokens=int(usage["input_tokens"]),
            output_tokens=int(usage["output_tokens"]),
            cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
            reasoning_tokens=int(usage.get("reasoning_tokens", 0)),
            cost_usd=cost,
        )

        with self._lock:
            self._spent += cost
            self._calls.append(call)
            spent = self._spent

        logger.info(
            "llm_call provider=%s model=%s input=%d cached=%d output=%d "
            "reasoning=%d cost_usd=%.6f spent_usd=%.6f limit_usd=%s",
            call.provider,
            call.model,
            call.input_tokens,
            call.cached_input_tokens,
            call.output_tokens,
            call.reasoning_tokens,
            cost,
            spent,
            self._limit,
        )

        if spent >= self._limit:
            logger.warning(
                "budget_exhausted spent_usd=%.6f limit_usd=%s; "
                "further calls will be blocked",
                spent,
                self._limit,
            )

        return call
