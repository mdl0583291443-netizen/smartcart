"""IngestionRun: an operational envelope, not a transaction boundary.

Proves the envelope can be opened, referenced by an occurrence, and
closed -- nothing more. Round 1 does not orchestrate a real collector run
end to end (see Round 1 governance: "Do not implement final ingestion
orchestration").
"""

from __future__ import annotations

from datetime import UTC, datetime

import pg8000.native

from smartcart.db_spike.catalog import get_or_create_store_by_alias, upsert_chain, upsert_subchain
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.ingestion_run import finish_ingestion_run, start_ingestion_run
from smartcart.db_spike.occurrence import get_occurrence, insert_occurrence

_CHAIN_ID = "7290027600007"
_SUBCHAIN_ID = "002"
_FILENAME_STORE_TOKEN = "413"


def test_ingestion_run_can_be_started_and_finished(db_conn: pg8000.native.Connection) -> None:
    started_at = datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)
    run = start_ingestion_run(db_conn, source="shufersal", started_at=started_at)

    row = db_conn.run(
        "SELECT source, started_at, finished_at FROM ingestion_run WHERE ingestion_run_id = :id",
        id=run.ingestion_run_id,
    )[0]
    assert row[0] == "shufersal"
    assert row[2] is None  # not finished yet

    finished_at = datetime(2026, 9, 7, 6, 5, 0, tzinfo=UTC)
    finish_ingestion_run(db_conn, ingestion_run_id=run.ingestion_run_id, finished_at=finished_at)

    row = db_conn.run(
        "SELECT finished_at FROM ingestion_run WHERE ingestion_run_id = :id",
        id=run.ingestion_run_id,
    )[0]
    assert row[0] is not None


def test_occurrence_may_reference_an_ingestion_run(db_conn: pg8000.native.Connection) -> None:
    upsert_chain(db_conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(db_conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")
    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="shufersal",
        alias_context="filename_store_id",
        raw_value=_FILENAME_STORE_TOKEN,
        store_name="Test Store",
    )

    run = start_ingestion_run(
        db_conn, source="shufersal", started_at=datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC)
    )
    content = insert_or_get_content(db_conn, b"<Root><Items></Items></Root>")

    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=run.ingestion_run_id,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...gz",
        schema_family=None,
        collected_at=datetime(2026, 9, 7, 6, 1, 0, tzinfo=UTC),
        validation_status="valid",
    )

    row = get_occurrence(db_conn, occurrence.occurrence_id)
    assert row is not None
    assert row["ingestion_run_id"] == run.ingestion_run_id
