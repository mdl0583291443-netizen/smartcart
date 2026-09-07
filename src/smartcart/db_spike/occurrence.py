"""ArtifactOccurrence persistence: fact/provenance of observing one
ArtifactContent in one source context (Fixed Data Invariant 2).

Validation outcome is recorded here, on the occurrence, never on
ArtifactContent -- it is a fact about this particular observation, not an
immutable property of the payload bytes (the same bytes could in
principle be observed again with a different validation outcome under
different validation logic, though this spike does not exercise that).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import pg8000.native

_KNOWN_VALIDATION_STATUSES = ("valid", "parse_failed", "validation_failed")


@dataclass(frozen=True)
class OccurrenceRecord:
    occurrence_id: int


def insert_occurrence(
    conn: pg8000.native.Connection,
    *,
    content_id: int,
    ingestion_run_id: int | None,
    chain_id: str,
    store_id: int | None,
    artifact_kind: str,
    source_filename: str | None,
    schema_family: str | None,
    collected_at: datetime,
    validation_status: str,
    validation_detail: dict[str, object] | None = None,
) -> OccurrenceRecord:
    """Record one observation of already-durable content.

    store_id is SmartCart's opaque Store surrogate identity (see
    catalog.py), never a retailer raw store identifier -- resolve it via
    catalog.get_or_create_store_by_alias first. None for a chain-scoped
    artifact_kind ("stores"); required for a store-scoped one
    ("pricefull") -- enforced by a database CHECK constraint.

    collected_at must already be timezone-aware UTC, captured immediately
    after successful artifact acquisition (Fixed Data Invariant 4) -- this
    function does not validate or coerce that; it cannot be reconstructed
    after the fact, so it is the caller's responsibility to pass the right
    value at the right moment.
    """
    if validation_status not in _KNOWN_VALIDATION_STATUSES:
        raise ValueError(
            f"Unknown validation_status {validation_status!r}; expected one of "
            f"{_KNOWN_VALIDATION_STATUSES}."
        )
    rows = conn.run(
        """
        INSERT INTO artifact_occurrence (
            content_id, ingestion_run_id, chain_id, store_id, artifact_kind,
            source_filename, schema_family, collected_at, validation_status, validation_detail
        ) VALUES (
            :content_id, :ingestion_run_id, :chain_id, :store_id, :artifact_kind,
            :source_filename, :schema_family, :collected_at, :validation_status, :validation_detail
        ) RETURNING occurrence_id
        """,
        content_id=content_id,
        ingestion_run_id=ingestion_run_id,
        chain_id=chain_id,
        store_id=store_id,
        artifact_kind=artifact_kind,
        source_filename=source_filename,
        schema_family=schema_family,
        collected_at=collected_at,
        validation_status=validation_status,
        validation_detail=json.dumps(validation_detail or {}),
    )
    return OccurrenceRecord(occurrence_id=rows[0][0])


def get_occurrence(conn: pg8000.native.Connection, occurrence_id: int) -> dict[str, object] | None:
    """Test/inspection helper: one occurrence's stored fields by id."""
    rows = conn.run(
        """
        SELECT occurrence_id, content_id, ingestion_run_id, chain_id, store_id, artifact_kind,
               source_filename, schema_family, collected_at, validation_status, validation_detail,
               activation_completed_at, activation_outcome
        FROM artifact_occurrence WHERE occurrence_id = :occurrence_id
        """,
        occurrence_id=occurrence_id,
    )
    if not rows:
        return None
    columns = [c["name"] for c in conn.columns]
    return dict(zip(columns, rows[0], strict=True))


def occurrences_for_content(conn: pg8000.native.Connection, content_id: int) -> list[int]:
    """Test/inspection helper: occurrence_ids referencing one content_id,
    in insertion order."""
    rows = conn.run(
        "SELECT occurrence_id FROM artifact_occurrence "
        "WHERE content_id = :content_id ORDER BY occurrence_id",
        content_id=content_id,
    )
    return [row[0] for row in rows]
