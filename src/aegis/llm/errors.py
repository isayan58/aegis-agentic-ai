"""
Aegis error types for provider failures.

Raw provider errors can contain request details or a partly masked API key
(OpenAI's 401 message echoes the key's first and last characters). The
gateway converts the common failures into these types, which keep only the
provider, the model and the HTTP status. The original exception is not
chained, so its text never reaches a traceback, a log or an API response.
"""

import openai


class ProviderError(RuntimeError):
    """Base class for a provider failure with no raw provider text."""

    reason = "provider call failed"

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.status_code = status_code

        status = f", status={status_code}" if status_code is not None else ""
        super().__init__(
            f"{self.reason} (provider={provider}, model={model}{status})"
        )

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(provider={self.provider!r}, "
            f"model={self.model!r}, status_code={self.status_code!r})"
        )


class ProviderAuthError(ProviderError):
    """The API key is wrong, expired or not allowed to use this model."""

    reason = "authentication failed: check the API key"


class ProviderNotFoundError(ProviderError):
    """The model or deployment name, or the base URL path, is wrong."""

    reason = "model or deployment not found: check its name and the base URL"


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached, timed out or is overloaded."""

    reason = "provider unreachable or unavailable"


def translate_provider_error(
    exc: BaseException,
    *,
    provider: str,
    model: str,
) -> ProviderError | None:
    """Map an OpenAI SDK exception to an Aegis error, or return None.

    Errors that are not mapped (for example a 400 for a malformed request)
    are left to the caller unchanged, because they point to a bug in our
    request rather than a misconfigured provider.
    """

    status_code = getattr(exc, "status_code", None)

    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        error_type: type[ProviderError] = ProviderAuthError
    elif isinstance(exc, openai.NotFoundError):
        error_type = ProviderNotFoundError
    elif isinstance(
        exc,
        (
            # APITimeoutError is a subclass of APIConnectionError.
            openai.APIConnectionError,
            openai.InternalServerError,
            openai.RateLimitError,
        ),
    ):
        error_type = ProviderUnavailableError
    else:
        return None

    return error_type(
        provider=provider,
        model=model,
        status_code=status_code,
    )
