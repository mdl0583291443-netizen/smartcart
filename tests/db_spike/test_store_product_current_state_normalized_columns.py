"""RED tests for Schema Slice 1 (ADR 0011): the six new normalized-fact/
provenance columns that will be added to store_product_current_state.

The production migration implementing this slice does not exist yet -- that
is intentional. These tests describe the observable database schema only
(column presence, PostgreSQL type, nullability, absence of a default) and
the real-Postgres domain enforcement for normalization_contract_version.
They deliberately do not assert migration filename/number, constraint name,
physical column order, SQL formatting, or any ORM/implementation detail.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pg8000.native
import pytest

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

# (column_name, expected information_schema.columns.data_type)
_EXPECTED_NORMALIZED_COLUMNS = [
    ("product_name", "text"),
    ("declared_quantity", "numeric"),
    ("declared_quantity_raw", "text"),
    ("declared_quantity_unit_raw", "text"),
    ("is_weighted", "boolean"),
    ("normalization_contract_version", "integer"),
]


def _seed(conn: pg8000.native.Connection) -> tuple[int, int]:
    """Returns (store_id, occurrence_id). Mirrors
    tests/db_spike/test_activation.py's own _seed helper."""
    upsert_chain(conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")
    store_id = get_or_create_store_by_alias(
        conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="shufersal",
        alias_context="filename_store_id",
        raw_value="413",
        store_name="Test Store",
    )
    upsert_chain_product(conn, chain_id=_CHAIN_ID, item_code_raw=_ITEM_CODE_RAW)

    content = insert_or_get_content(conn, b"<Root><Items><Item/></Items></Root>")
    occurrence = insert_occurrence(
        conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...gz",
        schema_family=None,
        collected_at=datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC),
        validation_status="valid",
    )
    return store_id, occurrence.occurrence_id


def _insert_current_state_row(
    conn: pg8000.native.Connection,
    *,
    store_id: int,
    occurrence_id: int,
    normalization_contract_version: int | None,
) -> None:
    conn.run(
        """
        INSERT INTO store_product_current_state (
            chain_id, store_id, item_code_raw, current_price, current_price_raw,
            source_occurrence_id, updated_at, normalization_contract_version
        ) VALUES (
            :chain_id, :store_id, :item_code_raw, :price, :price_raw,
            :occurrence_id, :updated_at, :normalization_contract_version
        )
        """,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        item_code_raw=_ITEM_CODE_RAW,
        price="6.90",
        price_raw="6.90",
        occurrence_id=occurrence_id,
        updated_at=datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC),
        normalization_contract_version=normalization_contract_version,
    )


# --- GROUP A1: schema shape -------------------------------------------------


@pytest.mark.parametrize(
    ("column_name", "expected_data_type"),
    _EXPECTED_NORMALIZED_COLUMNS,
    ids=[c[0] for c in _EXPECTED_NORMALIZED_COLUMNS],
)
def test_store_product_current_state_has_normalized_column(
    db_conn: pg8000.native.Connection, column_name: str, expected_data_type: str
) -> None:
    """Each of the six approved columns must exist on
    store_product_current_state as the specified PostgreSQL type, nullable,
    with no default."""
    rows = db_conn.run(
        """
        SELECT data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'store_product_current_state'
          AND column_name = :column_name
        """,
        column_name=column_name,
    )
    assert len(rows) == 1, (
        f"expected exactly one {column_name!r} column on "
        f"store_product_current_state; found {len(rows)}"
    )
    data_type, is_nullable, column_default = rows[0]
    assert data_type == expected_data_type
    assert is_nullable == "YES"
    assert column_default is None


# --- GROUP A2: normalization_contract_version domain ------------------------


@pytest.mark.parametrize(
    "value",
    [None, 1, 2],
    ids=["null-accepted", "one-accepted", "two-accepted"],
)
def test_normalization_contract_version_accepts_expected_value(
    db_conn: pg8000.native.Connection, value: int | None
) -> None:
    store_id, occurrence_id = _seed(db_conn)

    _insert_current_state_row(
        db_conn,
        store_id=store_id,
        occurrence_id=occurrence_id,
        normalization_contract_version=value,
    )

    rows = db_conn.run(
        """
        SELECT normalization_contract_version FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        item_code_raw=_ITEM_CODE_RAW,
    )
    assert rows[0][0] == value


def test_normalization_contract_version_zero_is_rejected_by_database(
    db_conn: pg8000.native.Connection,
) -> None:
    """0 must be rejected by a real database-enforced constraint (a CHECK
    violation, SQLSTATE 23514) -- not merely by any error at all. Asserting
    only "some DatabaseError was raised" would trivially and falsely
    "pass" today, since inserting a still-nonexistent column already
    raises DatabaseError (undefined_column, SQLSTATE 42703) for an
    unrelated reason. Asserting the specific SQLSTATE keeps this failure
    meaningful before the column/constraint exist, and only lets the test
    pass once the real CHECK constraint is what rejects the value."""
    store_id, occurrence_id = _seed(db_conn)

    with pytest.raises(pg8000.native.DatabaseError) as exc_info:
        _insert_current_state_row(
            db_conn,
            store_id=store_id,
            occurrence_id=occurrence_id,
            normalization_contract_version=0,
        )

    assert exc_info.value.args[0]["C"] == "23514"  # check_violation
