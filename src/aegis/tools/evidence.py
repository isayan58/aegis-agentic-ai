"""Load approved local fixtures and produce traceable evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aegis.schemas import (
    EvidenceItem,
    NonEmptyText,
    ResearchBundle,
    SourceRecord,
)
from aegis.state import make_evidence_id


class StrictModel(BaseModel):
    """Reject unexpected fields, type coercion, NaN, and infinity."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class FootballRow(StrictModel):
    """One fictional player-season-competition observation."""

    subject: NonEmptyText
    season: NonEmptyText
    competition: NonEmptyText
    matches: int = Field(ge=0)
    minutes: int = Field(ge=0)
    goals: int = Field(ge=0)
    assists: int = Field(ge=0)
    key_passes: int = Field(ge=0)


class PlatformRow(StrictModel):
    """One fictional platform specification."""

    subject: NonEmptyText
    storage_usd_tb_month: float = Field(ge=0)
    compute_usd_hour: float = Field(ge=0)
    certifications: list[NonEmptyText] = Field(min_length=1)
    sla_percent: float = Field(ge=0, le=100)
    regions: list[NonEmptyText] = Field(min_length=1)


class Fixture(StrictModel):
    """A versioned dataset containing exactly one kind of row."""

    title: NonEmptyText
    dataset_ref: NonEmptyText
    is_test_data: Literal[True]
    kind: Literal["football", "platforms"]
    rows: list[FootballRow | PlatformRow] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rows(self):
        """Enforce the row type and reject duplicate observations."""

        expected_type = (
            FootballRow if self.kind == "football" else PlatformRow
        )

        identities = []

        for row in self.rows:
            if not isinstance(row, expected_type):
                raise ValueError("Row type does not match fixture kind")

            if isinstance(row, FootballRow):
                identity = (
                    row.subject.casefold(),
                    row.season.casefold(),
                    row.competition.casefold(),
                )
            else:
                identity = (row.subject.casefold(),)

            identities.append(identity)

        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate fixture observations")

        return self


class EvidenceLookup(BaseModel):
    """Return an explicit gap when the fixture cannot answer a lookup."""

    model_config = ConfigDict(extra="forbid")

    source: SourceRecord | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reason: str | None = None


# Resolve relative to this module, not the notebook's working directory.
# This layout assumes the project's editable development installation.
FIXTURE_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "data" / "fixtures"
)

# Only these references may be opened. Inputs cannot choose arbitrary paths.
FIXTURE_FILES = {
    "football_demo_v1": "football_demo_v1.json",
    "platforms_demo_v1": "platforms_demo_v1.json",
}


# These mappings belong to the fixture adapters, not to the general graph.
FACTOR_FIELDS = {
    "football": {
        "scoring": ("goals", "minutes"),
        "creativity": ("assists", "key_passes", "minutes"),
        "availability": ("matches", "minutes"),
    },
    "platforms": {
        "operating cost": (
            "storage_usd_tb_month",
            "compute_usd_hour",
        ),
        "security": ("certifications",),
        "reliability": ("sla_percent",),
        "coverage": ("regions",),
    },
}


def load_fixture(dataset_ref: str) -> Fixture:
    """Load and validate one allowlisted fictional dataset."""

    filename = FIXTURE_FILES.get(dataset_ref)

    if filename is None:
        raise ValueError(f"Unknown fixture: {dataset_ref}")

    path = FIXTURE_DIRECTORY / filename

    # Validate the entire file before using any of its records.
    fixture = Fixture.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    if fixture.dataset_ref != dataset_ref:
        raise ValueError("Fixture header does not match requested reference")

    return fixture


def lookup_evidence(
    subject: str,
    factor: str,
    dataset_ref: str,
) -> EvidenceLookup:
    """Find observations for one subject and supported fixture factor."""

    fixture = load_fixture(dataset_ref)

    canonical_factor = factor.strip().casefold()
    fields = FACTOR_FIELDS[fixture.kind].get(canonical_factor)

    if fields is None:
        return EvidenceLookup(
            reason=f"Unsupported factor for this fixture: {factor}"
        )

    matching_rows = [
        row
        for row in fixture.rows
        if row.subject.casefold() == subject.strip().casefold()
    ]

    if not matching_rows:
        return EvidenceLookup(
            reason=f"Subject not found in this fixture: {subject}"
        )

    source = SourceRecord(
        source_id=f"src_{fixture.dataset_ref}",
        title=fixture.title,
        kind="dataset",
        dataset_ref=fixture.dataset_ref,
        retrieved_at=datetime.now(timezone.utc),
        is_test_data=True,
    )

    records = []

    for row in matching_rows:
        # A locator identifies the observation independently of row order.
        if isinstance(row, FootballRow):
            identity = [row.subject, row.season, row.competition]
            period = row.season
            coverage = row.competition
        else:
            identity = [row.subject]
            period = "Fictional v1 snapshot"
            coverage = "Fictional platform specifications"

        locator = json.dumps(identity, ensure_ascii=False)

        # Preserve the values and context; do not invent an interpretation.
        row_data = row.model_dump()
        selected = {
            "subject": row.subject,
            **{field: row_data[field] for field in fields},
        }

        record = EvidenceItem(
            evidence_id=make_evidence_id(
                source.source_id,
                locator,
                row.subject,
                canonical_factor,
                time_period=period,
                coverage=coverage,
            ),
            source_id=source.source_id,
            subject=row.subject,
            factor=canonical_factor,
            excerpt=json.dumps(selected, sort_keys=True),
            locator=locator,
            time_period=period,
            coverage=coverage,
        )

        records.append(record)

    # Confirm that every returned evidence item references this source.
    ResearchBundle(sources=[source], evidence=records)

    return EvidenceLookup(source=source, evidence=records)