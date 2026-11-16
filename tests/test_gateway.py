from unittest.mock import Mock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from aegis.config import Settings
from aegis.llm import gateway
from aegis.llm.usage import extract_usage


@pytest.fixture
def fake_settings():
    return Settings(
        _env_file=None,
        openai_api_key="fake-openai-key",
        openai_model="gpt-4o-mini",
        azure_openai_api_key="fake-azure-key",
        azure_openai_base_url=(
            "https://example.openai.azure.com/openai/v1/"
        ),
        azure_openai_deployment="gpt-5-mini",
    )


@pytest.mark.parametrize(
    "provider, expected_model, expected_key, expected_url",
    [
        (
            "openai",
            "gpt-4o-mini",
            "fake-openai-key",
            "https://api.openai.com/v1",
        ),
        (
            "azure",
            "gpt-5-mini",
            "fake-azure-key",
            "https://example.openai.azure.com/openai/v1/",
        ),
    ],
)
def test_provider_routing(
    monkeypatch,
    fake_settings,
    provider,
    expected_model,
    expected_key,
    expected_url,
):
    fake_model = FakeListChatModel(responses=["Offline response"])
    constructor = Mock(return_value=fake_model)

    monkeypatch.setattr(gateway, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(gateway, "ChatOpenAI", constructor)

    model = gateway.get_model(provider)

    assert model.invoke("Hello").content == "Offline response"
    constructor.assert_called_once()

    arguments = constructor.call_args.kwargs
    assert arguments["model"] == expected_model
    assert arguments["api_key"] == expected_key
    assert arguments["base_url"] == expected_url
    assert arguments["max_retries"] == 0


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="Provider must be"):
        gateway.get_model("unknown")


def test_usage_preserves_token_subsets():
    response = AIMessage(
        content="Done",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 30,
            "total_tokens": 130,
            "input_token_details": {"cache_read": 40},
            "output_token_details": {"reasoning": 20},
        },
    )

    usage = extract_usage(
        response,
        provider="azure",
        requested_model="gpt-5-mini",
    )

    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 30
    assert usage["total_tokens"] == 130
    assert usage["cached_input_tokens"] == 40
    assert usage["reasoning_tokens"] == 20


def test_missing_usage_is_not_treated_as_free():
    response = AIMessage(content="No usage supplied")

    with pytest.raises(ValueError, match="token usage"):
        extract_usage(
            response,
            provider="azure",
            requested_model="gpt-5-mini",
        )