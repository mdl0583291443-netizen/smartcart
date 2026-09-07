"""Round 1 tests 3, 4, 6: multiple ArtifactOccurrences may reference one
ArtifactContent with distinct provenance/collected_at, content dedup does
not erase occurrence provenance, and a parse/validation-failed occurrence
can preserve Content+Occurrence without creating any derived state.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pg8000.native

from smartcart.db_spike.catalog import get_or_create_store_by_alias, upsert_chain, upsert_subchain
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import get_occurrence, insert_occurrence, occurrences_for_content

_CHAIN_ID = "7290058140886"
_SUBCHAIN_ID = "001"
_FILENAME_STORE_TOKEN = "039"


def _seed_store(conn: pg8000.native.Connection) -> int:
    upsert_chain(conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")
    return get_or_create_store_by_alias(
        conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value=_FILENAME_STORE_TOKEN,
        store_name="Test Store",
    )


def test_two_occurrences_may_reference_the_same_content_with_distinct_provenance(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = _seed_store(db_conn)
    content = insert_or_get_content(db_conn, b"<Root><Items></Items></Root>")

    first = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...-0600.gz",
        schema_family="standard",
        collected_at=datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC),
        validation_status="valid",
    )
    second = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...-1200.gz",
        schema_family="standard",
        collected_at=datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC),
        validation_status="valid",
    )

    assert first.occurrence_id != second.occurrence_id
    assert set(occurrences_for_content(db_conn, content.content_id)) == {
        first.occurrence_id,
        second.occurrence_id,
    }

    first_row = get_occurrence(db_conn, first.occurrence_id)
    second_row = get_occurrence(db_conn, second.occurrence_id)
    assert first_row is not None
    assert second_row is not None
    assert first_row["collected_at"] != second_row["collected_at"]
    assert first_row["source_filename"] != second_row["source_filename"]


def test_content_deduplication_does_not_erase_occurrence_provenance(
    db_conn: pg8000.native.Connection,
) -> None:
    """The same underlying bytes observed on two separate occasions must
    still dedupe to one ArtifactContent while both observations remain
    individually visible with their own provenance."""
    store_id = _seed_store(db_conn)
    payload = b"<Root><Items></Items></Root>"

    content_a = insert_or_get_content(db_conn, payload)
    occurrence_a = insert_occurrence(
        db_conn,
        content_id=content_a.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="a.gz",
        schema_family="standard",
        collected_at=datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC),
        validation_status="valid",
    )

    content_b = insert_or_get_content(db_conn, payload)  # identical bytes, separate call
    occurrence_b = insert_occurrence(
        db_conn,
        content_id=content_b.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="b.gz",
        schema_family="standard",
        collected_at=datetime(2026, 9, 7, 12, 0, 0, tzinfo=UTC),
        validation_status="valid",
    )

    assert content_a.content_id == content_b.content_id
    assert occurrence_a.occurrence_id != occurrence_b.occurrence_id
    assert occurrences_for_content(db_conn, content_a.content_id) == sorted(
        [occurrence_a.occurrence_id, occurrence_b.occurrence_id]
    )


def test_parse_failed_occurrence_preserves_content_and_occurrence_without_derived_state(
    db_conn: pg8000.native.Connection,
) -> None:
    """A malformed-XML failure still has a complete, successfully
    transport-normalized/extracted payload (the canonical-content boundary
    established in the Collector Contract Inspection is pre-parser), so
    Content and Occurrence both persist -- but no CurrentState/
    PriceHistory row is ever written for a non-'valid' occurrence."""
    store_id = _seed_store(db_conn)
    content = insert_or_get_content(db_conn, b"<Root><Unclosed>")

    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="broken.gz",
        schema_family=None,
        collected_at=datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC),
        validation_status="parse_failed",
        validation_detail={"error": "Malformed PriceFull XML"},
    )

    row = get_occurrence(db_conn, occurrence.occurrence_id)
    assert row is not None
    assert row["validation_status"] == "parse_failed"
    assert row["content_id"] == content.content_id

    derived_state_count = db_conn.run(
        "SELECT count(*) FROM store_product_current_state "
        "WHERE source_occurrence_id = :occurrence_id",
        occurrence_id=occurrence.occurrence_id,
    )[0][0]
    derived_history_count = db_conn.run(
        "SELECT count(*) FROM price_history WHERE source_occurrence_id = :occurrence_id",
        occurrence_id=occurrence.occurrence_id,
    )[0][0]
    assert derived_state_count == 0
    assert derived_history_count == 0
