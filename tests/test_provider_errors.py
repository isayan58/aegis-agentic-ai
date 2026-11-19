"""Offline tests: provider exceptions become Aegis errors with no raw text."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_openai import ChatOpenAI

import aegis.api.main as api
from aegis.config import Settings
from aegis.llm import gateway
from aegis.llm.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    translate_provider_error,
)

# Stands in for the partly masked key OpenAI echoes back in a 401 message.
LEAKED_TEXT = "Incorrect API key provided: sk-SECRET-SENTINEL-1234"

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def status_error(error_type, status_code):
    return error_type(
        LEAKED_TEXT,
        response=httpx.Response(status_code, request=REQUEST),
        body={"error": {"message": LEAKED_TEXT}},
    )


CASES = [
    (status_error(openai.AuthenticationError, 401), ProviderAuthError, 401),
    (status_error(openai.PermissionDeniedError, 403), ProviderAuthError, 403),
    (status_error(openai.NotFoundError, 404), ProviderNotFoundError, 404),
    (status_error(openai.RateLimitError, 429), ProviderUnavailableError, 429),
    (status_error(openai.InternalServerError, 503), ProviderUnavailableError, 503),
    (openai.APIConnectionError(message=LEAKED_TEXT, request=REQUEST), ProviderUnavailableError, None),
    (openai.APITimeoutError(request=REQUEST), ProviderUnavailableError, None),
]


@pytest.mark.parametrize("raw, expected_type, status_code", CASES)
def test_translation_keeps_provider_and_drops_raw_text(raw, expected_type, status_code):
    error = translate_provider_error(raw, provider="openai", model="gpt-5.4")

    assert type(error) is expected_type
    assert error.provider == "openai"
    assert error.model == "gpt-5.4"
    assert error.status_code == status_code
    assert "SECRET-SENTINEL" not in str(error)
    assert "SECRET-SENTINEL" not in repr(error)


def test_unmapped_errors_are_left_alone():
    raw = status_error(openai.BadRequestError, 400)

    assert translate_provider_error(raw, provider="openai", model="gpt-5.4") is None


@pytest.fixture
def model(monkeypatch):
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-SECRET-SENTINEL-1234",
        azure_openai_api_key="fake-azure-key",
        azure_openai_base_url="https://example.openai.azure.com/openai/v1/",
        azure_openai_deployment="gpt-5-mini",
    )
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    return gateway.get_model("planner")


@pytest.mark.parametrize("raw, expected_type, status_code", CASES)
def test_gateway_model_raises_aegis_errors(monkeypatch, caplog, model, raw, expected_type, status_code):
    def fail(*args, **kwargs):
        raise raw

    # Fail inside the parent class, where the real HTTP call would happen.
    monkeypatch.setattr(ChatOpenAI, "_generate", fail)

    with pytest.raises(expected_type) as caught:
        model.invoke("hello")

    error = caught.value
    assert error.provider == "openai"
    # The raw provider exception is not chained, so it can't be printed.
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    for text in (str(error), repr(error), caplog.text):
        assert "SECRET-SENTINEL" not in text


def test_gateway_stream_raises_aegis_errors(monkeypatch, model):
    def fail(*args, **kwargs):
        raise status_error(openai.AuthenticationError, 401)
        yield  # makes this a generator, like the real _stream

    monkeypatch.setattr(ChatOpenAI, "_stream", fail)

    with pytest.raises(ProviderAuthError):
        list(model.stream("hello"))


def test_unmapped_error_passes_through(monkeypatch, model):
    raw = status_error(openai.BadRequestError, 400)

    def fail(*args, **kwargs):
        raise raw

    monkeypatch.setattr(ChatOpenAI, "_generate", fail)

    with pytest.raises(openai.BadRequestError):
        model.invoke("hello")


def test_ready_checks_config_only_and_never_calls_a_provider(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("/ready must not call a provider")

    # Any OpenAI SDK request, sync or async, would fail the test.
    monkeypatch.setattr(openai.OpenAI, "post", no_network)
    monkeypatch.setattr(openai.AsyncOpenAI, "post", no_network)
    monkeypatch.setattr(gateway, "_build_model", no_network)
    monkeypatch.setattr(api, "get_settings", lambda: object())

    with TestClient(api.app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "check": "configuration"}
