"""
This creates one place for configuring both providers. For now, it selects by provider; we’ll add role routing and budget enforcement separately.
"""


from typing import Literal

from langchain_openai import ChatOpenAI

from aegis.config import get_settings


Provider = Literal["openai", "azure"]


def get_model(provider: Provider = "azure") -> ChatOpenAI:
    if provider not in ("openai", "azure"):
        raise ValueError("Provider must be 'openai' or 'azure'")

    settings = get_settings()

    if provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url="https://api.openai.com/v1",
            max_tokens=128,
            timeout=60,
            max_retries=0,
        )

    # These model parameters are for your GPT-5 mini deployment.
    return ChatOpenAI(
        model=settings.azure_openai_deployment,
        api_key=settings.azure_openai_api_key.get_secret_value(),
        base_url=settings.azure_openai_base_url,
        reasoning_effort="minimal",
        max_completion_tokens=1024,
        timeout=60,
        max_retries=0,
    )