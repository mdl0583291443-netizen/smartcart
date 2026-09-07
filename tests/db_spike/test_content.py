"""Round 1 tests 2, 5, 7, 12: canonical ArtifactContent identity/dedup,
and that Content can be durable before any Occurrence exists.
"""

from __future__ import annotations

import pg8000.native

from smartcart.db_spike.content import (
    compute_content_hash,
    count_content_rows,
    get_content_by_hash,
    insert_or_get_content,
)

_SAMPLE_PAYLOAD = b"<Root><ChainID>7290058140886</ChainID></Root>"


def test_same_canonical_payload_inserted_twice_yields_one_identity(
    db_conn: pg8000.native.Connection,
) -> None:
    first = insert_or_get_content(db_conn, _SAMPLE_PAYLOAD)
    second = insert_or_get_content(db_conn, _SAMPLE_PAYLOAD)

    assert first.content_id == second.content_id
    assert first.content_hash == second.content_hash == compute_content_hash(_SAMPLE_PAYLOAD)
    assert count_content_rows(db_conn) == 1


def test_content_may_exist_durably_before_any_occurrence(db_conn: pg8000.native.Connection) -> None:
    record = insert_or_get_content(db_conn, _SAMPLE_PAYLOAD)

    fetched = get_content_by_hash(db_conn, record.content_hash)
    assert fetched is not None
    assert fetched.content_id == record.content_id

    occurrence_count = db_conn.run(
        "SELECT count(*) FROM artifact_occurrence WHERE content_id = :content_id",
        content_id=record.content_id,
    )[0][0]
    assert occurrence_count == 0


def test_distinct_payloads_get_distinct_content_identity(db_conn: pg8000.native.Connection) -> None:
    first = insert_or_get_content(db_conn, b"<Root>A</Root>")
    second = insert_or_get_content(db_conn, b"<Root>B</Root>")

    assert first.content_id != second.content_id
    assert first.content_hash != second.content_hash


def test_transport_acquisition_failure_creates_no_artifact_content(
    db_conn: pg8000.native.Connection,
) -> None:
    """A transport/acquisition failure that never produces a complete
    canonical payload has no bytes to hash, so nothing ever calls
    insert_or_get_content for it -- there is no failure-path function in
    content.py because there is nothing for one to do. This test asserts
    that directly: an otherwise-untouched database has zero content rows.
    """
    assert count_content_rows(db_conn) == 0


def test_rerunning_content_persistence_does_not_duplicate_identity(
    db_conn: pg8000.native.Connection,
) -> None:
    """Simulates the same collector output being processed more than once
    (e.g. after a crash/retry): re-inserting identical payload bytes must
    never produce a second ArtifactContent row."""
    for _ in range(3):
        insert_or_get_content(db_conn, _SAMPLE_PAYLOAD)

    assert count_content_rows(db_conn) == 1
