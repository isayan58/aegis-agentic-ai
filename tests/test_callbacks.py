import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from aegis.config import Settings
from aegis.llm.budget import BudgetExceededError, BudgetTracker
from aegis.llm.callbacks import (
    BudgetCallbackHandler,
    MissingModelMetadataError,
    new_run_budget,
)
from aegis.llm.pricing import UnknownModelPriceError

# gpt-5-mini: 1,000 input ($0.00025) + 500 output ($0.001) = $0.00125
CALL_COST = Decimal("0.00125")


def reply(input_tokens=1_000, output_tokens=500, usage=True):
    return AIMessage(
        content="ok",
        usage_metadata=(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
            if usage
            else None
        ),
    )


def fake_model(*messages, provider="azure", model="gpt-5-mini", metadata=True):
    """A fake chat model tagged the same way get_model(role) tags real ones."""

    return GenericFakeChatModel(
        messages=iter(messages),
        metadata=(
            {
                "aegis_role": "researcher",
                "aegis_provider": provider,
                "aegis_model": model,
            }
            if metadata
            else None
        ),
    )


def test_handler_raises_errors_instead_of_swallowing_them():
    assert BudgetCallbackHandler.raise_error is True


def test_each_call_is_recorded_without_extra_code():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply(), reply())

    model.invoke("first", config=config)
    model.invoke("second", config=config)

    assert len(tracker.calls) == 2
    assert tracker.spent_usd == CALL_COST * 2
    assert tracker.calls[0].provider == "azure"
    assert tracker.calls[0].model == "gpt-5-mini"
    assert tracker.calls[0].input_tokens == 1_000


def test_invoke_is_blocked_once_over_the_cap():
    # 1M gpt-5-mini input tokens cost $0.25, well over the $0.01 cap.
    tracker = BudgetTracker("0.01")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply(input_tokens=1_000_000, output_tokens=0), reply())

    model.invoke("expensive", config=config)

    with pytest.raises(BudgetExceededError):
        model.invoke("blocked", config=config)

    # The blocked call never ran, so nothing more was recorded.
    assert len(tracker.calls) == 1


def test_missing_usage_fails_instead_of_costing_zero():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply(usage=False))

    with pytest.raises(ValueError, match="token usage"):
        model.invoke("no usage", config=config)

    assert tracker.calls == ()


def test_model_without_aegis_metadata_is_rejected():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply(), metadata=False)

    with pytest.raises(MissingModelMetadataError, match="get_model"):
        model.invoke("untagged", config=config)


def test_unpriced_model_fails_loudly():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply(), model="unpriced-model")

    with pytest.raises(UnknownModelPriceError):
        model.invoke("unpriced", config=config)


class UsageStreamingFake(GenericFakeChatModel):
    """Streams like ChatOpenAI with stream_usage=True: usage on the last chunk.

    GenericFakeChatModel drops usage_metadata when streaming, so it can't
    stand in for a real streamed call here.
    """

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for text in ["o", "k"]:
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager:
                run_manager.on_llm_new_token(text, chunk=chunk)
            yield chunk

        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 1_000, "output_tokens": 500, "total_tokens": 1_500},
            )
        )


def test_streamed_call_is_recorded_once():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = UsageStreamingFake(
        messages=iter([]),
        metadata={"aegis_provider": "azure", "aegis_model": "gpt-5-mini"},
    )

    chunks = list(model.stream("stream", config=config))

    assert "".join(chunk.content for chunk in chunks) == "ok"
    assert len(tracker.calls) == 1
    assert tracker.spent_usd == CALL_COST


def test_async_call_is_recorded():
    tracker = BudgetTracker("1.00")
    config = {"callbacks": [BudgetCallbackHandler(tracker)]}
    model = fake_model(reply())

    asyncio.run(model.ainvoke("async", config=config))

    assert len(tracker.calls) == 1


def test_parallel_calls_share_one_handler():
    tracker = BudgetTracker("100")
    handler = BudgetCallbackHandler(tracker)
    config = {"callbacks": [handler]}

    def call(_):
        # One model per worker: the fake's message iterator isn't thread-safe.
        fake_model(reply()).invoke("parallel", config=config)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(call, range(40)))

    assert len(tracker.calls) == 40
    assert tracker.spent_usd == CALL_COST * 40
    # Every started run was matched with its end.
    assert handler._runs == {}


def test_new_run_budget_uses_the_configured_limit():
    settings = Settings(
        _env_file=None,
        openai_api_key="fake-openai-key",
        azure_openai_api_key="fake-azure-key",
        azure_openai_base_url="https://example.openai.azure.com/openai/v1/",
        azure_openai_deployment="gpt-5-mini",
        budget_limit_usd="0.50",
    )

    tracker, config = new_run_budget(settings)

    assert tracker.limit_usd == Decimal("0.50")
    assert len(config["callbacks"]) == 1
    assert config["callbacks"][0].tracker is tracker

    fake_model(reply()).invoke("hello", config=config)
    assert len(tracker.calls) == 1
