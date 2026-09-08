"""RED test for Schema Slice 1 (ADR 0011), Group K: legacy migration
compatibility / no backfill.

Proves a genuine upgrade path: a store_product_current_state row inserted
against today's schema (migrations 0001-0003, the state immediately
preceding the not-yet-existing Schema Slice 1 migration) must survive
applying whatever migration(s) exist next, with all pre-existing values
unchanged and all six new normalized/provenance columns NULL.

This test never hardcodes a future migration filename or number: it drives
the upgrade purely through the existing migrate.apply_migrations() harness,
which applies whatever .sql files exist in db_spike/migrations/ in filename
order. Today, that call is a no-op (the db_conn fixture already applied
every migration that currently exists) -- the migration-application step
itself is not expected to raise. The meaningful RED signal is the final
assertion, which selects the six not-yet-existing columns and must fail
with a real "column does not exist" database error, not a fixture/setup
failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pg8000.native

from smartcart.db_spike import migrate
from smartcart.db_spike.activation import PriceObservation, record_price_observation
from smartcart.db_spike.catalog import (
    get_or_create_store_by_alias,
    upsert_chain,
    upsert_chain_product,
    upsert_subchain,
)
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import insert_occurrence

_CHAIN_ID = "7290027600007"
_SUBCHAIN_ID = "002"
_ITEM_CODE_RAW = "10181040009"
_LEGACY_PRICE = Decimal("46.50")
_LEGACY_PRICE_RAW = "46.50"
_LEGACY_OBSERVED_AT = datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC)

_NEW_NORMALIZED_COLUMNS = (
    "product_name",
    "declared_quantity",
    "declared_quantity_raw",
    "declared_quantity_unit_raw",
    "is_weighted",
    "normalization_contract_version",
)


def test_legacy_current_state_row_survives_upgrade_with_new_columns_null(
    db_conn: pg8000.native.Connection,
) -> None:
    # --- Step 1 & 2: seed identity and insert one valid legacy row against
    # today's schema (migrations 0001-0003 only -- the db_conn fixture has
    # already applied exactly these and nothing more, since no Schema
    # Slice 1 migration exists yet). This must succeed cleanly so that a
    # fixture/setup failure is distinguishable from the expected RED below.
    upsert_chain(db_conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(db_conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")
    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="shufersal",
        alias_context="filename_store_id",
        raw_value="413",
        store_name="Test Store",
    )
    upsert_chain_product(db_conn, chain_id=_CHAIN_ID, item_code_raw=_ITEM_CODE_RAW)
    content = insert_or_get_content(db_conn, b"<Root><Items><Item/></Items></Root>")
    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...gz",
        schema_family=None,
        collected_at=_LEGACY_OBSERVED_AT,
        validation_status="valid",
    )

    record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=_CHAIN_ID,
            store_id=store_id,
            item_code_raw=_ITEM_CODE_RAW,
            price=_LEGACY_PRICE,
            price_raw=_LEGACY_PRICE_RAW,
            observed_at=_LEGACY_OBSERVED_AT,
            source_occurrence_id=occurrence.occurrence_id,
        ),
    )

    # Sanity checkpoint: the legacy row exists with the expected pre-existing
    # values *before* any upgrade attempt -- proves setup succeeded on its
    # own merits, independent of the RED assertion below.
    pre_upgrade_rows = db_conn.run(
        """
        SELECT current_price, current_price_raw, source_occurrence_id
        FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        item_code_raw=_ITEM_CODE_RAW,
    )
    assert len(pre_upgrade_rows) == 1
    assert pre_upgrade_rows[0][0] == _LEGACY_PRICE
    assert pre_upgrade_rows[0][1] == _LEGACY_PRICE_RAW
    assert pre_upgrade_rows[0][2] == occurrence.occurrence_id

    # --- Step 3: attempt to apply the next/remaining migration(s) through
    # the existing harness only -- no filename/number is named here. Today
    # this is a no-op (everything that exists was already applied by the
    # db_conn fixture); once the Schema Slice 1 migration exists, this call
    # is what actually applies it.
    migrate.apply_migrations(db_conn)

    # --- Step 4: the legacy row must still exist, with pre-existing values
    # unchanged, and all six new columns NULL.
    post_upgrade_rows = db_conn.run(
        f"""
        SELECT current_price, current_price_raw, source_occurrence_id,
               {", ".join(_NEW_NORMALIZED_COLUMNS)}
        FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        item_code_raw=_ITEM_CODE_RAW,
    )
    assert len(post_upgrade_rows) == 1
    row = post_upgrade_rows[0]
    assert row[0] == _LEGACY_PRICE
    assert row[1] == _LEGACY_PRICE_RAW
    assert row[2] == occurrence.occurrence_id
    for value in row[3:]:
        assert value is None
