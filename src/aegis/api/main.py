from fastapi import FastAPI, HTTPException, status
from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from aegis.config import get_settings


app = FastAPI(
    title="Aegis AI",
    description="API for Aegis agent workflows.",
    version="0.1.0",
)


@app.get("/health", tags=["Operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/ready",
    tags=["Operations"],
    responses={503: {"description": "Configuration is invalid"}},
)
def ready() -> dict[str, str]:
    try:
        get_settings()
    except (ValidationError, SettingsError):
        # Do not expose configuration values or raw validation errors.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application configuration is missing or invalid.",
        ) from None

    return {
        "status": "ready",
        "check": "configuration",
    }