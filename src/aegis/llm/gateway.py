"""
One place to build chat models. Graph nodes ask for a role and the settings
decide the provider and model:

    model = get_model("researcher")
    tracker, config = new_run_budget()
    model.invoke("...", config=config)   # checked and recorded automatically

Every model carries aegis_role, aegis_provider and aegis_model metadata, which
BudgetCallbackHandler uses to price the call. Common provider failures are
raised as ProviderAuthError, ProviderNotFoundError or ProviderUnavailableError,
with the raw provider text removed.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from aegis.config import ROLES, Provider, Role, RoleModel, get_settings
from aegis.llm.errors import translate_provider_error

OPENAI_BASE_URL = "https://api.openai.com/v1"


class AegisChatOpenAI(ChatOpenAI):
    """ChatOpenAI that turns provider failures into Aegis errors.

    Only the four low-level methods are wrapped, so invoke, stream, batch,
    bind_tools and with_structured_output all keep working unchanged.
    """

    aegis_provider: str
    aegis_model: str

    def _translate(self, exc: Exception) -> Exception:
        error = translate_provider_error(
            exc,
            provider=self.aegis_provider,
            model=self.aegis_model,
        )
        return error if error is not None else exc

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return super()._generate(*args, **kwargs)
        except Exception as exc:
            error = self._translate(exc)
            if error is exc:
                raise
            # "from None" drops the raw provider error from the traceback.
            raise error from None

    async def _agenerate(self, *args: Any, **kwargs: Any) -> ChatResult:
        try:
            return await super()._agenerate(*args, **kwargs)
        except Exception as exc:
            error = self._translate(exc)
            if error is exc:
                raise
            raise error from None

    def _stream(self, *args: Any, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        try:
            yield from super()._stream(*args, **kwargs)
        except Exception as exc:
            error = self._translate(exc)
            if error is exc:
                raise
            raise error from None

    async def _astream(
        self, *args: Any, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        try:
            async for chunk in super()._astream(*args, **kwargs):
                yield chunk
        except Exception as exc:
            error = self._translate(exc)
            if error is exc:
                raise
            raise error from None


def _build_model(
    provider: Provider,
    model: str,
    params: RoleModel,
    *,
    role: str,
) -> AegisChatOpenAI:
    settings = get_settings()

    if provider == "openai":
        api_key = settings.openai_api_key.get_secret_value()
        base_url = OPENAI_BASE_URL
    elif provider == "azure":
        api_key = settings.azure_openai_api_key.get_secret_value()
        base_url = settings.azure_openai_base_url
    else:
        raise ValueError("Provider must be 'openai' or 'azure'")

    # Both models are reasoning models, so both paths use
    # max_completion_tokens (which includes reasoning tokens) and an effort.
    optional: dict[str, Any] = {}
    if params.reasoning_effort is not None:
        optional["reasoning_effort"] = params.reasoning_effort

    return AegisChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_completion_tokens=params.max_completion_tokens,
        timeout=60,
        max_retries=0,
        # Streamed responses must report usage too, or the budget misses them.
        stream_usage=True,
        metadata={
            "aegis_role": role,
            "aegis_provider": provider,
            "aegis_model": model,
        },
        aegis_provider=provider,
        aegis_model=model,
        **optional,
    )


def get_model(role: Role) -> AegisChatOpenAI:
    """Return the chat model configured for a graph role."""

    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}")

    params = get_settings().role_models[role]
    return _build_model(params.provider, params.model, params, role=role)
