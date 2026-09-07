"""Round 1 tests 10, 11: a typed Decimal price coexists with the raw price
representation, and CurrentState/PriceHistory can reference their
originating occurrence.

No ordering/atomicity-under-concurrency claims are made here -- that is
Round 2 (see src/smartcart/db_spike/activation.py's module docstring).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pg8000.native

from smartcart.db_spike.activation import (
    PriceObservation,
    current_state,
    price_history_for,
    record_price_observation,
)
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
_FILENAME_STORE_TOKEN = "413"
_ITEM_CODE_RAW = "10181040009"


def _seed(conn: pg8000.native.Connection) -> tuple[int, int]:
    """Returns (store_id, occurrence_id)."""
    upsert_chain(conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")
    store_id = get_or_create_store_by_alias(
        conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="shufersal",
        alias_context="filename_store_id",
        raw_value=_FILENAME_STORE_TOKEN,
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


def test_typed_decimal_price_coexists_with_raw_price_representation(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id, occurrence_id = _seed(db_conn)

    record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=_CHAIN_ID,
            store_id=store_id,
            item_code_raw=_ITEM_CODE_RAW,
            price=Decimal("46.50"),
            price_raw="46.50",
            observed_at=datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC),
            source_occurrence_id=occurrence_id,
        ),
    )

    state = current_state(
        db_conn, chain_id=_CHAIN_ID, store_id=store_id, item_code_raw=_ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("46.50")
    assert state["current_price_raw"] == "46.50"


def test_current_state_and_price_history_reference_the_originating_occurrence(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id, occurrence_id = _seed(db_conn)

    history_id = record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=_CHAIN_ID,
            store_id=store_id,
            item_code_raw=_ITEM_CODE_RAW,
            price=Decimal("46.50"),
            price_raw="46.50",
            observed_at=datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC),
            source_occurrence_id=occurrence_id,
        ),
    )
    assert history_id > 0

    state = current_state(
        db_conn, chain_id=_CHAIN_ID, store_id=store_id, item_code_raw=_ITEM_CODE_RAW
    )
    history = price_history_for(
        db_conn, chain_id=_CHAIN_ID, store_id=store_id, item_code_raw=_ITEM_CODE_RAW
    )

    assert state is not None
    assert state["source_occurrence_id"] == occurrence_id
    assert len(history) == 1
    assert history[0]["source_occurrence_id"] == occurrence_id


def test_initial_observation_creates_an_initial_price_history_event(
    db_conn: pg8000.native.Connection,
) -> None:
    """PriceHistory is append-oriented: even the very first observation
    creates one event row, not merely a CurrentState row (Fixed Data
    Invariant 8 -- no valid_to interval model)."""
    store_id, occurrence_id = _seed(db_conn)

    record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=_CHAIN_ID,
            store_id=store_id,
            item_code_raw=_ITEM_CODE_RAW,
            price=Decimal("10.00"),
            price_raw="10.00",
            observed_at=datetime(2026, 9, 7, 6, 30, 0, tzinfo=UTC),
            source_occurrence_id=occurrence_id,
        ),
    )

    history = price_history_for(
        db_conn, chain_id=_CHAIN_ID, store_id=store_id, item_code_raw=_ITEM_CODE_RAW
    )
    assert len(history) == 1
