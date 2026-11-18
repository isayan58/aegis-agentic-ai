"""
This loads settings and stores API keys as SecretStr, which masks their values in normal printed representations. Explicitly calling .get_secret_value() still exposes the underlying value, so only use that when passing credentials to clients.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    openai_api_key: SecretStr
    openai_model: str = "gpt-4o-mini"

    azure_openai_api_key: SecretStr
    azure_openai_base_url: str
    azure_openai_deployment: str

    # Spending cutoff for one research run, measured in USD.
    budget_limit_usd: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        allow_inf_nan=False,
    )

    @field_validator("openai_api_key", "azure_openai_api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("API key must not be empty")
        return value

    @field_validator("azure_openai_base_url")
    @classmethod
    def validate_azure_url(cls, value: str) -> str:
        value = value.strip().rstrip("/") + "/"

        if not value.startswith("https://"):
            raise ValueError("Azure endpoint must use HTTPS")

        if not value.endswith("/openai/v1/"):
            raise ValueError("Azure endpoint must end in /openai/v1/")

        return value

    @field_validator("azure_openai_deployment", "openai_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model or deployment name must not be empty")
        return value.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()