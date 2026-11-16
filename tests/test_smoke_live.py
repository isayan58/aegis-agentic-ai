import pytest

from aegis.config import get_settings
from aegis.llm.gateway import get_model
from aegis.llm.usage import extract_usage


@pytest.mark.live
@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_live_provider(provider):
    try:
        settings = get_settings()
        model = get_model(provider)
        response = model.invoke("Say hello in one short sentence.")

        requested_model = (
            settings.openai_model
            if provider == "openai"
            else settings.azure_openai_deployment
        )

        usage = extract_usage(
            response,
            provider=provider,
            requested_model=requested_model,
        )
    except Exception as exc:
        # Avoid including raw provider errors or credentials in output.
        pytest.fail(
            f"{provider} live test failed: {type(exc).__name__}",
            pytrace=False,
        )

    assert response.content, "Provider returned empty content"
    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0
    assert usage["total_tokens"] == (
        usage["input_tokens"] + usage["output_tokens"]
    )