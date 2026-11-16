from fastapi.testclient import TestClient
from pydantic_settings.exceptions import SettingsError

import aegis.api.main as api


def test_ready_with_valid_configuration(monkeypatch):
    # The endpoint only needs the settings validation to succeed.
    monkeypatch.setattr(api, "get_settings", lambda: object())

    with TestClient(api.app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "check": "configuration",
    }


def test_invalid_configuration_is_safe(monkeypatch):
    secret_marker = "DO-NOT-EXPOSE-THIS"

    def broken_settings():
        raise SettingsError(secret_marker)

    monkeypatch.setattr(api, "get_settings", broken_settings)

    with TestClient(api.app) as client:
        health = client.get("/health")
        readiness = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    assert readiness.status_code == 503
    assert readiness.json() == {
        "detail": "Application configuration is missing or invalid."
    }
    assert secret_marker not in readiness.text