import logging

import pytest
from langchain_core.messages import AIMessage

from aegis.config import ROLES, Settings
from aegis.llm import gateway
from aegis.llm.usage import extract_usage


def make_settings(**overrides):
    values = dict(
        _env_file=None,
        openai_api_key="fake-openai-key",
        openai_model="gpt-5.4",
        azure_openai_api_key="fake-azure-key",
        azure_openai_base_url="https://example.openai.azure.com/openai/v1/",
        azure_openai_deployment="gpt-5-mini",
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def fake_settings(monkeypatch):
    # conftest.py already removes ROLE_MODELS__* variables from the shell.
    settings = make_settings()
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    return settings


# --- role routing ----------------------------------------------------------


@pytest.mark.parametrize(
    "role, provider, model, key, url",
    [
        ("planner", "openai", "gpt-5.4", "fake-openai-key", "https://api.openai.com/v1"),
        ("judge", "openai", "gpt-5.4", "fake-openai-key", "https://api.openai.com/v1"),
        ("reporter", "openai", "gpt-5.4", "fake-openai-key", "https://api.openai.com/v1"),
        ("researcher", "azure", "gpt-5-mini", "fake-azure-key", "https://example.openai.azure.com/openai/v1/"),
        ("analyst", "azure", "gpt-5-mini", "fake-azure-key", "https://example.openai.azure.com/openai/v1/"),
    ],
)
def test_each_role_resolves_to_its_provider_and_model(
    fake_settings, role, provider, model, key, url
):
    llm = gateway.get_model(role)

    assert llm.model_name == model
    assert llm.openai_api_key.get_secret_value() == key
    assert llm.openai_api_base == url
    assert llm.max_retries == 0
    assert llm.metadata["aegis_role"] == role
    assert llm.metadata["aegis_provider"] == provider
    assert llm.metadata["aegis_model"] == model


def test_judge_and_researcher_use_different_providers(fake_settings):
    judge = gateway.get_model("judge")
    researcher = gateway.get_model("researcher")

    assert judge.metadata["aegis_provider"] != researcher.metadata["aegis_provider"]


def test_openai_path_uses_reasoning_parameters(fake_settings):
    llm = gateway.get_model("planner")

    # gpt-5.4 is a reasoning model: the limit must include reasoning tokens.
    assert llm.max_tokens == fake_settings.role_models["planner"].max_completion_tokens
    assert llm.reasoning_effort == "low"
    assert llm.stream_usage is True


def test_unknown_role_rejected(fake_settings):
    with pytest.raises(ValueError, match="Role must be one of"):
        gateway.get_model("unknown")


def test_defaults_cover_every_role():
    settings = make_settings()

    assert set(settings.role_models) == set(ROLES)


def test_role_can_be_overridden_from_environment(monkeypatch):
    monkeypatch.setenv("ROLE_MODELS__JUDGE__PROVIDER", "azure")
    monkeypatch.setenv("ROLE_MODELS__REPORTER__MAX_COMPLETION_TOKENS", "8192")

    settings = make_settings()

    # Overridden fields change; everything else keeps its default.
    assert settings.role_models["judge"].provider == "azure"
    assert settings.role_models["judge"].model == "gpt-5-mini"
    assert settings.role_models["reporter"].max_completion_tokens == 8192
    assert settings.role_models["reporter"].provider == "openai"
    assert settings.role_models["planner"].model == "gpt-5.4"


def test_unpriced_role_model_fails_at_startup():
    with pytest.raises(ValueError, match="No price configured for role models"):
        make_settings(role_models={"planner": {"model": "not-a-priced-model"}})


def test_unknown_role_in_settings_rejected():
    with pytest.raises(ValueError, match="Unknown roles"):
        make_settings(role_models={"critic": {"provider": "openai"}})


def test_warns_when_judge_shares_provider_with_researcher(caplog):
    with caplog.at_level(logging.WARNING, logger="aegis.config"):
        make_settings(role_models={"judge": {"provider": "azure"}})

    assert "judge and researcher both use provider=azure" in caplog.text


def test_no_warning_with_default_providers(caplog):
    with caplog.at_level(logging.WARNING, logger="aegis.config"):
        make_settings()

    assert "judge and researcher" not in caplog.text


# --- usage extraction ------------------------------------------------------


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
