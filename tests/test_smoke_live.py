import pytest

from aegis.config import ROLES, get_settings
from aegis.llm.callbacks import new_run_budget
from aegis.llm.gateway import get_model


def distinct_pairs():
    """One role for each distinct (provider, model) pair, so each is called once."""

    pairs: dict[tuple[str, str], str] = {}
    for role in ROLES:
        config = get_settings().role_models[role]
        pairs.setdefault((config.provider, config.model), role)
    return pairs


@pytest.mark.live
def test_each_provider_model_pair_once():
    pairs = distinct_pairs()
    tracker, config = new_run_budget()

    for (provider, model_name), role in pairs.items():
        try:
            response = get_model(role).invoke(
                "Say hello in one short sentence.",
                config=config,
            )
        except Exception as exc:
            # Avoid including raw provider errors or credentials in output.
            pytest.fail(
                f"{provider}/{model_name} (role={role}) failed: {type(exc).__name__}",
                pytrace=False,
            )

        assert response.content, f"{provider}/{model_name} returned empty content"

    # The callbacks recorded every call with no extra code.
    assert len(tracker.calls) == len(pairs)
    assert {(call.provider, call.model) for call in tracker.calls} == set(pairs)

    for call in tracker.calls:
        assert call.input_tokens > 0
        assert call.output_tokens > 0
        assert call.cost_usd > 0
