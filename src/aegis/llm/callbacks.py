"""
Checks and records every model call in a run, with no code in each node.

    tracker, config = new_run_budget()
    get_model("researcher").invoke("...", config=config)
    graph.invoke(state, config=config)   # callbacks reach every nested call
    print(tracker.spent_usd, tracker.calls)

Before each chat model call the handler runs tracker.check(); after it, the
handler reads usage_metadata from the response and runs tracker.record().
Models must come from get_model(role), which attaches the aegis_provider and
aegis_model metadata used for pricing. A call without that metadata fails
instead of going unrecorded.
"""

import threading
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableConfig

from aegis.config import Settings, get_settings
from aegis.llm.budget import BudgetTracker
from aegis.llm.usage import extract_usage


class MissingModelMetadataError(RuntimeError):
    """Raised when a model call can't be attributed to a provider and model."""


class BudgetCallbackHandler(BaseCallbackHandler):
    # Without this, LangChain logs handler exceptions and carries on, so a
    # BudgetExceededError would never stop the call.
    raise_error = True

    def __init__(self, tracker: BudgetTracker) -> None:
        self.tracker = tracker
        # Parallel graph branches share one handler, so guard the run map.
        self._runs: dict[UUID, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.tracker.check()

        metadata = metadata or {}
        provider = metadata.get("aegis_provider")
        model = metadata.get("aegis_model")

        if not provider or not model:
            raise MissingModelMetadataError(
                "Model call has no aegis_provider/aegis_model metadata; "
                "build models with get_model(role)."
            )

        with self._lock:
            self._runs[run_id] = (provider, model)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        with self._lock:
            run = self._runs.pop(run_id, None)

        if run is None:
            # Not a chat model call we started tracking (e.g. a plain LLM).
            return

        provider, model = run
        message = _first_message(response)

        # extract_usage raises if usage is missing, so a call is never free.
        usage = extract_usage(message, provider=provider, requested_model=model)
        self.tracker.record(usage)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # A failed call returns no usage; forget the run so the map stays small.
        with self._lock:
            self._runs.pop(run_id, None)


def _first_message(response: LLMResult) -> AIMessage:
    """Return the message that carries the call's usage.

    With n > 1 choices LangChain copies the same usage onto every choice,
    so only the first one is counted.
    """

    for generations in response.generations:
        for generation in generations:
            if isinstance(generation, ChatGeneration) and isinstance(
                generation.message, AIMessage
            ):
                return generation.message

    raise ValueError("Model response contained no chat message to read usage from")


def new_run_budget(
    settings: Settings | None = None,
) -> tuple[BudgetTracker, RunnableConfig]:
    """Create a tracker for one run and the config that enforces it."""

    settings = settings or get_settings()
    tracker = BudgetTracker(settings.budget_limit_usd)
    config: RunnableConfig = {"callbacks": [BudgetCallbackHandler(tracker)]}
    return tracker, config
