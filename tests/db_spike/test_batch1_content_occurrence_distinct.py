"""SmartCart Ingestion TDD -- Tests First, Batch 1: T11A.

Frozen RED Plan classification: EXPECTED_GREEN_REGRESSION. Requirements:
R12A, R12C.

Test seam: the existing content/occurrence persistence API
(content.insert_or_get_content, occurrence.insert_occurrence,
occurrence.get_occurrence, occurrence.occurrences_for_content), against a
real, ephemeral Postgres instance (db_conn, from tests/db_spike/conftest.py
-- not modified).

PROVENANCE: SYNTHETIC_TEST_FIXTURE. Every fixture value in this file
(_SAME_BYTES, filenames, collected_at timestamps) has NO physical-artifact
source -- none is derived from, or intended as evidence about, any real
market artifact. They follow the exact seeding pattern already established
in tests/db_spike/round2_support.py (imported, not duplicated).

This is deliberately NOT a T11B test: it proves only that the STRUCTURAL
capability already confirmed present by direct code/schema inspection
(content dedup by hash, distinct occurrence identity, two occurrences
legitimately referencing one content row, independent per-occurrence
provenance) is exercised together in one test, end to end -- it makes no
claim about activation/CurrentState/PriceHistory factual effects, which is
T11B's separate, not-yet-in-scope claim.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pg8000.native

from db_spike.round2_support import CHAIN_ID, seed_store
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import get_occurrence, insert_occurrence, occurrences_for_content

_SAME_BYTES = b"<Root><ChainID>7290027600007</ChainID><Items></Items></Root>"


def test_t11a_identical_bytes_dedupe_to_one_content_with_two_independent_occurrences(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)

    # 1/2. Insert/store identical raw bytes twice through the existing
    # content API; confirm they deduplicate to one content identity.
    content_a = insert_or_get_content(db_conn, _SAME_BYTES)
    content_b = insert_or_get_content(db_conn, _SAME_BYTES)
    assert content_a.content_id == content_b.content_id
    assert content_a.content_hash == content_b.content_hash

    # 3/4. Create two legitimate, distinct occurrences referring to that
    # SAME content, each with its own distinct provenance/time context.
    collected_at_1 = datetime(2026, 9, 15, 6, 0, 0, tzinfo=UTC)
    collected_at_2 = datetime(2026, 9, 15, 6, 5, 0, tzinfo=UTC)

    occ_1 = insert_occurrence(
        db_conn,
        content_id=content_a.content_id,
        ingestion_run_id=None,
        chain_id=CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull7290027600007-002-413-20260915-060000.gz",
        schema_family="standard",
        collected_at=collected_at_1,
        validation_status="valid",
    )
    occ_2 = insert_occurrence(
        db_conn,
        content_id=content_a.content_id,
        ingestion_run_id=None,
        chain_id=CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull7290027600007-002-413-20260915-060500.gz",
        schema_family="standard",
        collected_at=collected_at_2,
        validation_status="valid",
    )

    # Two distinct occurrence_ids -- content dedup never collapses
    # occurrence identity.
    assert occ_1.occurrence_id != occ_2.occurrence_id

    # 5. Retrieve both occurrences; both remain independently queryable.
    row_1 = get_occurrence(db_conn, occ_1.occurrence_id)
    row_2 = get_occurrence(db_conn, occ_2.occurrence_id)
    assert row_1 is not None
    assert row_2 is not None

    # Both point at the SAME content_id (the whole point of this case).
    assert row_1["content_id"] == content_a.content_id
    assert row_2["content_id"] == content_a.content_id

    # Provenance/time context remains independent per occurrence -- content
    # hash never becomes, or substitutes for, occurrence identity.
    assert row_1["occurrence_id"] != row_2["occurrence_id"]
    assert row_1["collected_at"] == collected_at_1
    assert row_2["collected_at"] == collected_at_2
    assert row_1["source_filename"] != row_2["source_filename"]

    # The content/occurrence relationship is discoverable in both
    # directions: one content_id -> multiple occurrence_ids.
    linked = occurrences_for_content(db_conn, content_a.content_id)
    assert set(linked) == {occ_1.occurrence_id, occ_2.occurrence_id}
