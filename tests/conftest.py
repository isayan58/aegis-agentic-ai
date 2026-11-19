import os

import pytest

from aegis.config import get_settings


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run billable provider tests",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return

    skip_live = pytest.mark.skip(reason="Requires --run-live")

    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def isolate_test_state(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    # Role overrides in the shell must not change what offline tests expect.
    for name in list(os.environ):
        if name.upper().startswith("ROLE_MODELS__"):
            monkeypatch.delenv(name)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()