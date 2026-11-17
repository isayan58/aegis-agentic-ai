"""Offline checks for shared state, retries, and reference integrity."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from langgraph.graph import START, END, StateGraph
from pydantic import ValidationError

from aegis.reducers import append, merge_by_id, sum_usage
from aegis.schemas import EvidenceItem, SourceRecord
from aegis.state import (
    AegisState,
    bundle_from_state,
    make_evidence_id,
)


@pytest.fixture
def sample_records():
    """Build valid synthetic records without calling a provider."""

    source = SourceRecord(
        source_id="src_test_v1",
        title="Synthetic state test",
        kind="dataset",
        dataset_ref="fixture://state_test_v1",
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_test_data=True,
    )

    evidence = EvidenceItem(
        evidence_id=make_evidence_id(
            source.source_id,
            "row/1",
            "Player A",
            "Scoring",
        ),
        source_id=source.source_id,
        subject="Player A",
        factor="Scoring",
        excerpt="Synthetic goals: 8",
        locator="row/1",
    )

    return source, evidence


def test_merge_and_retry_do_not_mutate_inputs():
    current = {"ev_a": "original"}
    update = {"ev_b": "other"}

    merged = merge_by_id(current, update)
    corrected = merge_by_id(merged, {"ev_a": "corrected"})

    assert corrected == {
        "ev_a": "corrected",
        "ev_b": "other",
    }

    assert current == {"ev_a": "original"}
    assert merged["ev_a"] == "original"

    # Repeating the same update does not add a duplicate.
    assert merge_by_id(corrected, {"ev_a": "corrected"}) == corrected


def test_event_append_preserves_attempts():
    original = [{"attempt": 1}]

    result = append(original, [{"attempt": 2}])

    assert result == [{"attempt": 1}, {"attempt": 2}]
    assert original == [{"attempt": 1}]


def test_usage_adds_deltas():
    first = {
        "demo/model": {
            "tokens_in": 10,
            "tokens_out": 2,
            "cost_usd": Decimal("0.1"),
        }
    }

    second = {
        "demo/model": {
            "tokens_in": 5,
            "tokens_out": 3,
            "cost_usd": Decimal("0.2"),
        }
    }

    result = sum_usage(first, second)

    assert result["demo/model"] == {
        "tokens_in": 15,
        "tokens_out": 5,
        "cost_usd": Decimal("0.3"),
    }

    assert first["demo/model"]["tokens_in"] == 10


def test_evidence_ids_are_stable_and_scope_sensitive():
    identity = ("src", "row/1", "Player A", "Scoring")

    assert make_evidence_id(*identity) == make_evidence_id(*identity)

    assert make_evidence_id(
        *identity, time_period="2025"
    ) != make_evidence_id(
        *identity, time_period="2026"
    )


def test_parallel_merge_and_later_retry(sample_records):
    source, first = sample_records

    # Create a second valid observation with its own stable ID.
    second_data = first.model_dump()
    second_data.update(
        evidence_id=make_evidence_id(
            source.source_id, "row/2", "Player B", "Scoring"
        ),
        subject="Player B",
        locator="row/2",
    )
    second = EvidenceItem.model_validate(second_data)

    corrected_data = first.model_dump()
    corrected_data["excerpt"] = "Synthetic goals: 9"
    corrected = EvidenceItem.model_validate(corrected_data)

    def worker_a(state):
        return {"evidence": {first.evidence_id: first}}

    def worker_b(state):
        return {"evidence": {second.evidence_id: second}}

    def join(state):
        # The join must see both parallel updates.
        assert len(bundle_from_state(state).evidence) == 2
        return {}

    def retry_a(state):
        return {"evidence": {corrected.evidence_id: corrected}}

    graph = StateGraph(AegisState)
    graph.add_node("a", worker_a)
    graph.add_node("b", worker_b)
    graph.add_node("join", join)
    graph.add_node("retry_a", retry_a)

    graph.add_edge(START, "a")
    graph.add_edge(START, "b")
    graph.add_edge(["a", "b"], "join")
    graph.add_edge("join", "retry_a")
    graph.add_edge("retry_a", END)

    result = graph.compile().invoke(
        {"sources": {source.source_id: source}}
    )

    assert len(result["evidence"]) == 2
    assert result["evidence"][first.evidence_id].excerpt == (
        "Synthetic goals: 9"
    )
    assert result["evidence"][second.evidence_id] == second


def test_bundle_rejects_unknown_source(sample_records):
    _, evidence = sample_records

    with pytest.raises(ValidationError, match="unknown source"):
        bundle_from_state(
            {
                "sources": {},
                "evidence": {evidence.evidence_id: evidence},
            }
        )


def test_bundle_rejects_mismatched_dictionary_key(sample_records):
    source, _ = sample_records

    with pytest.raises(ValueError, match="dictionary key"):
        bundle_from_state(
            {"sources": {"incorrect_key": source}}
        )