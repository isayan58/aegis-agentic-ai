"""Prove that the metrics detect missing and unnecessary behavior."""

import pytest

from evals.evaluators import routing_matches, tool_metrics


def test_exact_tools():
    result = tool_metrics(["lookup", "calculate"], ["lookup", "calculate"])
    assert result["precision"] == 1
    assert result["recall"] == 1
    assert result["sequence_exact"] is True


def test_extra_tool_reduces_precision():
    result = tool_metrics(["lookup"], ["lookup", "lookup"])
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == 1


def test_missing_tool_reduces_recall():
    result = tool_metrics(["lookup", "calculate"], ["lookup"])
    assert result["precision"] == 1
    assert result["recall"] == pytest.approx(0.5)


def test_wrong_worker_fails():
    assert not routing_matches(
        [("evidence", "Player A", "scoring")],
        [("web", "Player A", "scoring")],
    )


def test_duplicate_task_fails():
    expected = [("evidence", "Player A", "scoring")]
    assert not routing_matches(expected, expected * 2)