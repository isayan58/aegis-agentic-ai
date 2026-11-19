"""
Live misconfiguration tests. Each request fails before any model runs, so
they cost nothing, but they do need network access and real settings.
"""

import logging

import pytest
from pydantic import SecretStr

from aegis.config import ROLES, RoleModel, get_settings
from aegis.llm import gateway
from aegis.llm.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)

FAKE_OPENAI_KEY = "sk-aegis-invalid-key-for-tests-0000000000000000"


def role_for(provider):
    settings = get_settings()
    for role in ROLES:
        if settings.role_models[role].provider == provider:
            return role
    pytest.skip(f"No role is configured for provider={provider}")


def use_settings(monkeypatch, **update):
    # model_copy skips validation, so a deliberately broken value gets through.
    broken = get_settings().model_copy(update=update)
    monkeypatch.setattr(gateway, "get_settings", lambda: broken)


def assert_no_secrets(error, caplog):
    settings = get_settings()
    secrets = [
        FAKE_OPENAI_KEY,
        settings.openai_api_key.get_secret_value(),
        settings.azure_openai_api_key.get_secret_value(),
    ]

    for text in (str(error), repr(error), caplog.text):
        for secret in secrets:
            assert secret not in text
            # OpenAI echoes the start and end of a wrong key; check both.
            assert secret[:8] not in text
            assert secret[-4:] not in text

    assert error.__cause__ is None


@pytest.mark.live
def test_wrong_openai_key_raises_auth_error(monkeypatch, caplog):
    role = role_for("openai")
    use_settings(monkeypatch, openai_api_key=SecretStr(FAKE_OPENAI_KEY))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderAuthError) as caught:
            gateway.get_model(role).invoke("hello")

    assert caught.value.provider == "openai"
    assert caught.value.status_code == 401
    assert_no_secrets(caught.value, caplog)


@pytest.mark.live
def test_wrong_azure_deployment_raises_not_found(monkeypatch, caplog):
    role = role_for("azure")
    settings = get_settings()
    role_models = {
        **settings.role_models,
        role: RoleModel(
            **{
                **settings.role_models[role].model_dump(),
                "model": "aegis-missing-deployment",
            }
        ),
    }
    use_settings(monkeypatch, role_models=role_models)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderNotFoundError) as caught:
            gateway.get_model(role).invoke("hello")

    assert caught.value.provider == "azure"
    assert caught.value.model == "aegis-missing-deployment"
    assert_no_secrets(caught.value, caplog)


@pytest.mark.live
def test_unreachable_base_url_raises_unavailable(monkeypatch, caplog):
    role = role_for("azure")
    # .invalid is reserved and never resolves, so this fails fast.
    use_settings(
        monkeypatch,
        azure_openai_base_url="https://aegis-unreachable.invalid/openai/v1/",
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderUnavailableError) as caught:
            gateway.get_model(role).invoke("hello")

    assert caught.value.provider == "azure"
    assert caught.value.status_code is None
    assert_no_secrets(caught.value, caplog)
