"""
This loads settings and stores API keys as SecretStr, which masks their values in normal printed representations. Explicitly calling .get_secret_value() still exposes the underlying value, so only use that when passing credentials to clients.

Graph nodes ask for a role ("planner", "judge", ...), and these settings decide
which provider and model serve it. Each role can be overridden from .env with
nested variables, for example:

    ROLE_MODELS__JUDGE__PROVIDER=azure
    ROLE_MODELS__JUDGE__MODEL=gpt-5-mini
    ROLE_MODELS__REPORTER__MAX_COMPLETION_TOKENS=8192

Anything not overridden keeps its default. A role with no model set uses
OPENAI_MODEL for OpenAI or AZURE_OPENAI_DEPLOYMENT for Azure.
"""

import logging
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aegis.llm.pricing import PRICES

logger = logging.getLogger(__name__)

Provider = Literal["openai", "azure"]
Role = Literal["planner", "researcher", "analyst", "judge", "reporter"]
ROLES: tuple[Role, ...] = get_args(Role)

# gpt-5.4 accepts none/low/medium/high/xhigh; gpt-5-mini accepts
# minimal/low/medium/high. The provider rejects a value the model doesn't support.
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]


class RoleModel(BaseModel):
    """Which provider and model serve one role, and with what limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    model: str
    # For reasoning models this budget covers reasoning and visible output.
    max_completion_tokens: int = Field(gt=0)
    reasoning_effort: ReasoningEffort | None = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Role model name must not be empty")
        return value.strip()


# Planner, judge and reporter need the stronger model. Researcher and analyst
# run many times per request, so they use the cheaper one. Keeping the judge on
# a different provider from the researcher means one model doesn't mark its
# own work.
DEFAULT_ROLE_MODELS: dict[Role, dict[str, Any]] = {
    "planner": {"provider": "openai", "max_completion_tokens": 4096, "reasoning_effort": "low"},
    "researcher": {"provider": "azure", "max_completion_tokens": 2048, "reasoning_effort": "minimal"},
    "analyst": {"provider": "azure", "max_completion_tokens": 2048, "reasoning_effort": "low"},
    "judge": {"provider": "openai", "max_completion_tokens": 2048, "reasoning_effort": "low"},
    "reporter": {"provider": "openai", "max_completion_tokens": 4096, "reasoning_effort": "low"},
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        env_nested_delimiter="__",
    )

    openai_api_key: SecretStr
    openai_model: str = "gpt-5.4"

    azure_openai_api_key: SecretStr
    azure_openai_base_url: str
    azure_openai_deployment: str

    # Spending cutoff for one research run, measured in USD.
    budget_limit_usd: Decimal = Field(
        default=Decimal("1.00"),
        gt=0,
        allow_inf_nan=False,
    )

    # Filled from DEFAULT_ROLE_MODELS plus any overrides; see the module docstring.
    role_models: dict[Role, RoleModel] = Field(default_factory=dict)

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

    @model_validator(mode="before")
    @classmethod
    def merge_role_defaults(cls, data: Any) -> Any:
        """Merge per-field overrides onto the defaults for every role.

        Without this, setting one variable such as ROLE_MODELS__JUDGE__MODEL
        would replace the whole mapping and drop the other roles.
        """

        if not isinstance(data, dict):
            return data

        overrides = data.get("role_models") or {}
        if not isinstance(overrides, dict):
            raise ValueError("role_models must be a mapping of role to settings")

        overrides = {str(role).lower(): value for role, value in overrides.items()}
        unknown = set(overrides) - set(ROLES)
        if unknown:
            raise ValueError(f"Unknown roles in role_models: {sorted(unknown)}")

        openai_model = str(data.get("openai_model") or "gpt-5.4").strip()
        azure_deployment = str(data.get("azure_openai_deployment") or "").strip()

        merged: dict[str, Any] = {}
        for role in ROLES:
            override = overrides.get(role) or {}
            if isinstance(override, RoleModel):
                merged[role] = override
                continue

            values = {**DEFAULT_ROLE_MODELS[role]}
            values.update({str(key).lower(): value for key, value in override.items()})

            if not values.get("model"):
                values["model"] = (
                    openai_model if values.get("provider") == "openai" else azure_deployment
                )

            merged[role] = values

        return {**data, "role_models": merged}

    @model_validator(mode="after")
    def check_role_models(self) -> "Settings":
        # Fail at startup, not on the first call, if a role can't be costed.
        unpriced = {
            role: config.model
            for role, config in self.role_models.items()
            if config.model not in PRICES
        }
        if unpriced:
            details = ", ".join(f"{role}={model}" for role, model in sorted(unpriced.items()))
            raise ValueError(f"No price configured for role models: {details}. Add them to PRICES.")

        if self.role_models["judge"].provider == self.role_models["researcher"].provider:
            logger.warning(
                "judge and researcher both use provider=%s; the verifier will be "
                "checking output from the same provider",
                self.role_models["judge"].provider,
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
