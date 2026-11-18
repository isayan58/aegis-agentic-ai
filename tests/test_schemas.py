"""Regression tests for request schemas and evidence integrity."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from aegis.schemas import (
    ResearchBundle,
    ResearchRequest,
    SourceRecord,
)


@pytest.fixture
def request_payload():
    """Provide a complete, valid comparison request for each test."""

    return {
        "objective": "Compare fictional players.",
        "subjects": ["Player A", "Player B"],
        "factors": ["Scoring", "Creativity"],
        "mode": "compare",
        "scope": {
            "time_period": "2024–2025",
            "coverage": "Demo League",
        },
    }


@pytest.mark.parametrize(
    "subjects,factors",
    [
        (
            ["Player A", "Player B"],
            ["Scoring", "Creativity"],
        ),
        (
            ["Vendor A", "Vendor B"],
            ["Operating cost", "Security"],
        ),
    ],
)
def test_valid_requests_are_accepted(request_payload, subjects, factors):
    """The request schema supports different research domains."""

    request_payload["objective"] = "Compare the selected subjects."
    request_payload["subjects"] = subjects
    request_payload["factors"] = factors
    request_payload["scope"] = {
        "time_period": "Fictional test period",
        "coverage": "Synthetic comparison data",
    }

    request = ResearchRequest.model_validate(request_payload)

    assert request.subjects == subjects
    assert request.factors == factors
    assert request.mode == "compare"


@pytest.mark.parametrize(
    "patch,error_fragment",
    [
        (
            {"subjects": ["Player A"]},
            "requires at least two subjects",
        ),
        (
            {"subjects": ["Player A", "player a"]},
            "Subjects must be unique",
        ),
        (
            {"factors": ["Scoring", "scoring"]},
            "Factors must be unique",
        ),
        (
            {"unexpected_setting": True},
            "Extra inputs are not permitted",
        ),
    ],
)
def test_invalid_requests_are_rejected(
    request_payload,
    patch,
    error_fragment,
):
    """Reject each malformed request for the intended reason."""

    request_payload.update(patch)

    with pytest.raises(ValidationError, match=error_fragment):
        ResearchRequest.model_validate(request_payload)


@pytest.fixture
def source_payload():
    """Common source fields; each test adds its location information."""

    return {
        "source_id": "src_demo",
        "title": "Synthetic source for schema tests",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "is_test_data": True,
    }


@pytest.mark.parametrize(
    "location",
    [
        {
            "kind": "web",
            "url": "https://example.com/synthetic-evidence",
        },
        {
            "kind": "dataset",
            "dataset_ref": "fixture://schema_demo_v1",
        },
    ],
)
def test_valid_source_locations_are_accepted(source_payload, location):
    """Web and dataset sources use their respective location fields."""

    source = SourceRecord.model_validate(
        {**source_payload, **location}
    )

    assert source.kind == location["kind"]
    assert source.is_test_data is True


@pytest.mark.parametrize(
    "location,error_fragment",
    [
        (
            {"kind": "web"},
            "Web sources require a URL",
        ),
        (
            {"kind": "dataset"},
            "Dataset sources require dataset_ref",
        ),
        (
            {
                "kind": "web",
                "url": "https://example.com/synthetic-evidence",
                "dataset_ref": "fixture://schema_demo_v1",
            },
            "Web sources require a URL and no dataset_ref",
        ),
        (
            {
                "kind": "dataset",
                "dataset_ref": "fixture://schema_demo_v1",
                "url": "https://example.com/synthetic-evidence",
            },
            "Dataset sources require dataset_ref and no URL",
        ),
    ],
)
def test_invalid_source_locations_are_rejected(
    source_payload,
    location,
    error_fragment,
):
    """Reject missing or conflicting source locations."""

    with pytest.raises(ValidationError, match=error_fragment):
        SourceRecord.model_validate(
            {**source_payload, **location}
        )


@pytest.fixture
def bundle_payload():
    """Build a complete source → evidence → finding relationship."""

    return {
        "sources": [
            {
                "source_id": "src_demo",
                "title": "Synthetic evidence dataset",
                "kind": "dataset",
                "dataset_ref": "fixture://schema_demo_v1",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "is_test_data": True,
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev_demo",
                "source_id": "src_demo",
                "subject": "Player A",
                "factor": "Scoring",
                "excerpt": "Synthetic goals: 12",
                "locator": "players/Player A/2024",
            }
        ],
        "findings": [
            {
                "finding_id": "finding_demo",
                "subject": "Player A",
                "factor": "Scoring",
                "claim": "The synthetic row records 12 goals.",
                "claim_type": "reported_fact",
                "evidence_ids": ["ev_demo"],
            }
        ],
    }


def test_valid_bundle_is_accepted(bundle_payload):
    """A finding can cite evidence that points to an existing source."""

    bundle = ResearchBundle.model_validate(bundle_payload)

    assert len(bundle.sources) == 1
    assert len(bundle.evidence) == 1
    assert len(bundle.findings) == 1

    assert bundle.evidence[0].source_id == bundle.sources[0].source_id
    assert bundle.findings[0].evidence_ids == [
        bundle.evidence[0].evidence_id
    ]

    # A newly created finding must not claim to be verified.
    assert bundle.findings[0].verification_status == "unverified"


@pytest.mark.parametrize(
    "problem,error_fragment",
    [
        ("unknown_source", "unknown source"),
        ("unknown_evidence", "unknown evidence"),
        ("duplicate_source", "Duplicate source IDs"),
        ("duplicate_evidence", "Duplicate evidence IDs"),
        ("duplicate_finding", "Duplicate finding IDs"),
        ("repeated_citation", "repeats evidence IDs"),
    ],
)
def test_bundle_rejects_invalid_references(
    bundle_payload,
    problem,
    error_fragment,
):
    """Break one relationship or identity rule at a time."""

    payload = deepcopy(bundle_payload)

    if problem == "unknown_source":
        payload["evidence"][0]["source_id"] = "src_missing"

    elif problem == "unknown_evidence":
        payload["findings"][0]["evidence_ids"] = ["ev_missing"]

    elif problem == "duplicate_source":
        payload["sources"].append(
            deepcopy(payload["sources"][0])
        )

    elif problem == "duplicate_evidence":
        payload["evidence"].append(
            deepcopy(payload["evidence"][0])
        )

    elif problem == "duplicate_finding":
        payload["findings"].append(
            deepcopy(payload["findings"][0])
        )

    elif problem == "repeated_citation":
        payload["findings"][0]["evidence_ids"] = [
            "ev_demo",
            "ev_demo",
        ]

    with pytest.raises(ValidationError, match=error_fragment):
        ResearchBundle.model_validate(payload)