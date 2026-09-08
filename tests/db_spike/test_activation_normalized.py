"""RED tests for Schema Slice 2: normalized-fact persistence through the
existing Round-2 ordered/atomic activation engine.

Frozen architecture (approved, not invented here):

    from smartcart.db_spike.activation import NormalizedActivationItem

    NormalizedActivationItem(
        retailer_chain_id: str, resolved_store_id: int, item_code_raw: str,
        price: Decimal, price_raw: str, product_name: str,
        declared_quantity: Decimal, declared_quantity_raw: str,
        declared_quantity_unit_raw: str, is_weighted: bool | None,
        collected_at: datetime,
    )

    activate_occurrence(
        conn, *, occurrence_id, products: Sequence[ProductPrice],
        normalized_items: Sequence[NormalizedActivationItem] = (),
        on_checkpoint=None,
    ) -> ActivationOutcome

`NormalizedActivationItem` does not exist yet -- that is intentional. This
file is expected to fail at collection (ImportError) until it does, and to
fail at each call site (TypeError: unexpected keyword argument
'normalized_items') once it exists but `activate_occurrence` has not yet
been extended to accept it. `products=()` is always paired with a non-empty
`normalized_items` in every test here (the legacy/normalized XOR invariant),
since no test in this file needs to prove the XOR rule itself.

Reuses tests/db_spike/round2_support.py's existing seeding helpers
unmodified. `normalization_contract_version` is never supplied by a test --
per the frozen architecture it is assigned internally (== 1) by the
normalized persistence path, and is only ever asserted, never constructed.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pg8000.native
import pytest

from db_spike.round2_support import (
    CHAIN_ID,
    ITEM_CODE_RAW,
    ITEM_CODE_RAW_2,
    SUBCHAIN_ID,
    collected_at,
    make_occurrence,
    seed_products,
    seed_store,
)
from smartcart.db_spike.activation import (
    ActivationOutcome,
    NormalizedActivationItem,
    activate_occurrence,
    activation_outcome,
    activation_status,
    current_state,
    price_history_for,
)
from smartcart.db_spike.catalog import (
    get_or_create_store_by_alias,
    upsert_chain,
    upsert_subchain,
)

_NEW_NORMALIZED_COLUMNS = (
    "product_name",
    "declared_quantity",
    "declared_quantity_raw",
    "declared_quantity_unit_raw",
    "is_weighted",
    "normalization_contract_version",
)


def _normalized_item(
    *,
    chain_id: str = CHAIN_ID,
    store_id: int,
    item_code_raw: str = ITEM_CODE_RAW,
    price: str,
    price_raw: str | None = None,
    product_name: str,
    declared_quantity: str,
    declared_quantity_raw: str | None = None,
    declared_quantity_unit_raw: str,
    is_weighted: bool | None,
    collected_at_value: datetime,
) -> NormalizedActivationItem:
    return NormalizedActivationItem(
        retailer_chain_id=chain_id,
        resolved_store_id=store_id,
        item_code_raw=item_code_raw,
        price=Decimal(price),
        price_raw=price_raw if price_raw is not None else price,
        product_name=product_name,
        declared_quantity=Decimal(declared_quantity),
        declared_quantity_raw=(
            declared_quantity_raw if declared_quantity_raw is not None else declared_quantity
        ),
        declared_quantity_unit_raw=declared_quantity_unit_raw,
        is_weighted=is_weighted,
        collected_at=collected_at_value,
    )


def _normalized_current_state_row(
    conn: pg8000.native.Connection,
    *,
    store_id: int,
    item_code_raw: str,
    chain_id: str = CHAIN_ID,
) -> dict[str, object] | None:
    rows = conn.run(
        f"""
        SELECT {", ".join(_NEW_NORMALIZED_COLUMNS)}
        FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=chain_id,
        store_id=store_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    return dict(zip(_NEW_NORMALIZED_COLUMNS, rows[0], strict=True))


# --- B: first APPLIED normalized write -------------------------------------


def test_first_applied_normalized_write_populates_all_normalized_facts(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    item = _normalized_item(
        store_id=store_id,
        price="6.90",
        product_name="חלב טרי 3% תנובה 1 ליטר",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )

    outcome = activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])
    assert outcome == ActivationOutcome.APPLIED

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("6.90")
    assert state["current_price_raw"] == "6.90"
    assert state["source_occurrence_id"] == occ

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "חלב טרי 3% תנובה 1 ליטר"
    assert row["declared_quantity"] == Decimal("1")
    assert row["declared_quantity_raw"] == "1"
    assert row["declared_quantity_unit_raw"] == "Liter"
    assert row["is_weighted"] is False
    assert row["normalization_contract_version"] == 1


# --- C: newer APPLIED replaces all normalized facts coherently -------------


def test_newer_applied_normalized_observation_replaces_all_facts_coherently(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ1 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    item1 = _normalized_item(
        store_id=store_id,
        price="6.90",
        product_name="Old Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ1, products=(), normalized_items=[item1])
        == ActivationOutcome.APPLIED
    )

    occ2 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 5))
    item2 = _normalized_item(
        store_id=store_id,
        price="9.90",
        product_name="New Name",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 5),
    )
    outcome = activate_occurrence(
        db_conn, occurrence_id=occ2, products=(), normalized_items=[item2]
    )
    assert outcome == ActivationOutcome.APPLIED

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("9.90")
    assert state["current_price_raw"] == "9.90"

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "New Name"
    assert row["declared_quantity"] == Decimal("2")
    assert row["declared_quantity_raw"] == "2"
    assert row["declared_quantity_unit_raw"] == "Kilogram"
    assert row["is_weighted"] is True
    assert row["normalization_contract_version"] == 1


# --- D: STALE_PRESERVED does not mutate normalized facts -------------------


def test_stale_preserved_does_not_mutate_normalized_facts(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    newer_occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 10))
    newer_item = _normalized_item(
        store_id=store_id,
        price="9.90",
        product_name="Newer Name",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 10),
    )
    assert (
        activate_occurrence(
            db_conn, occurrence_id=newer_occ, products=(), normalized_items=[newer_item]
        )
        == ActivationOutcome.APPLIED
    )

    older_occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    older_item = _normalized_item(
        store_id=store_id,
        price="1.00",
        product_name="Stale Name",
        declared_quantity="99",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    outcome = activate_occurrence(
        db_conn, occurrence_id=older_occ, products=(), normalized_items=[older_item]
    )
    assert outcome == ActivationOutcome.STALE_PRESERVED

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("9.90")

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "Newer Name"
    assert row["declared_quantity"] == Decimal("2")
    assert row["declared_quantity_unit_raw"] == "Kilogram"
    assert row["is_weighted"] is True
    assert row["normalization_contract_version"] == 1


# --- E: ALREADY_APPLIED performs zero CurrentState writes -------------------


def test_already_applied_performs_zero_current_state_writes(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    item = _normalized_item(
        store_id=store_id,
        price="6.90",
        product_name="Original Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])
        == ActivationOutcome.APPLIED
    )

    # Fixture-level direct mutation to deliberate sentinel values -- proves
    # the idempotent retry below performs zero writes rather than merely
    # rewriting the same (correct) values back.
    db_conn.run(
        """
        UPDATE store_product_current_state
        SET current_price = :sentinel_price, product_name = :sentinel_name
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        sentinel_price=Decimal("999.99"),
        sentinel_name="SENTINEL",
        chain_id=CHAIN_ID,
        store_id=store_id,
        item_code_raw=ITEM_CODE_RAW,
    )

    outcome = activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])
    assert outcome == ActivationOutcome.ALREADY_APPLIED

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("999.99")

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "SENTINEL"


# --- F: normalized-only change does not create price_history ---------------


def test_normalized_only_change_does_not_create_price_history_event(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ1 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    item1 = _normalized_item(
        store_id=store_id,
        price="7.00",
        price_raw="7.00",
        product_name="Old Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ1, products=(), normalized_items=[item1])
        == ActivationOutcome.APPLIED
    )

    # 7.0 and 7.00 are the same typed Decimal value -- already-established
    # equal-Decimal/different-formatting semantics (see
    # test_activation_round2.py's identical test for plain ProductPrice).
    occ2 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 5))
    item2 = _normalized_item(
        store_id=store_id,
        price="7.0",
        price_raw="7.0",
        product_name="New Name",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 5),
    )
    outcome = activate_occurrence(
        db_conn, occurrence_id=occ2, products=(), normalized_items=[item2]
    )
    assert outcome == ActivationOutcome.APPLIED

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert len(history) == 1

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price_raw"] == "7.0"
    assert state["source_occurrence_id"] == occ2

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "New Name"
    assert row["declared_quantity"] == Decimal("2")
    assert row["is_weighted"] is True


# --- F3: price + normalized fact change composes correctly -----------------


def test_price_and_normalized_fact_change_composes_correctly(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ1 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    item1 = _normalized_item(
        store_id=store_id,
        price="7.00",
        product_name="Old Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ1, products=(), normalized_items=[item1])
        == ActivationOutcome.APPLIED
    )

    occ2 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 5))
    item2 = _normalized_item(
        store_id=store_id,
        price="6.50",
        product_name="New Name",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 5),
    )
    outcome = activate_occurrence(
        db_conn, occurrence_id=occ2, products=(), normalized_items=[item2]
    )
    assert outcome == ActivationOutcome.APPLIED

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("7.00"), Decimal("6.50")]

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("6.50")

    row = _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
    assert row is not None
    assert row["product_name"] == "New Name"
    assert row["declared_quantity"] == Decimal("2")
    assert row["is_weighted"] is True


# --- H: resolved store id reaches persistence -------------------------------


def test_resolved_store_id_reaches_persisted_current_state(
    db_conn: pg8000.native.Connection,
) -> None:
    """Positive normalized integration/smoke coverage only. This does NOT
    independently prove that item.resolved_store_id (rather than
    occurrence.store_id) is what the engine actually consumes: valid input
    requires the two to be equal (see I2), so this test alone cannot tell
    them apart. I2 (test_resolved_store_mismatch_fails_and_leaves_occurrence_unresolved)
    is the behavioral proof that item.resolved_store_id is actually read
    and validated. This test intentionally keeps that non-independent role
    -- it is not redesigned into a provenance-observable mechanism."""
    # Alias resolution used strictly as an existing black-box setup step --
    # not re-testing alias creation/resolution itself.
    upsert_chain(db_conn, chain_id=CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(db_conn, chain_id=CHAIN_ID, subchain_id=SUBCHAIN_ID, subchain_name="Test Sub")
    resolved_store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=CHAIN_ID,
        subchain_id=SUBCHAIN_ID,
        source="rami_levy",
        alias_context="xml_store_id_online",
        raw_value="39",
        store_name="Online Store",
    )
    seed_products(db_conn)
    occ = make_occurrence(
        db_conn, store_id=resolved_store_id, collected_at_value=collected_at(6, 0)
    )
    item = _normalized_item(
        store_id=resolved_store_id,
        price="24.90",
        product_name="מארז קוקה קולה 6 פחיות",
        declared_quantity="1.98",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )

    outcome = activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])
    assert outcome == ActivationOutcome.APPLIED

    rows = db_conn.run(
        "SELECT store_id FROM store_product_current_state "
        "WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw",
        chain_id=CHAIN_ID,
        item_code_raw=ITEM_CODE_RAW,
    )
    assert len(rows) == 1
    assert rows[0][0] == resolved_store_id


# --- I1/I2/I3: pre-mutation consistency guards ------------------------------


def test_chain_mismatch_fails_and_leaves_occurrence_unresolved(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    item = _normalized_item(
        chain_id="0000000000000",  # deliberately disagrees with occurrence.chain_id
        store_id=store_id,
        price="6.90",
        product_name="Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])

    assert (
        current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
        is None
    )
    assert (
        price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
        )
        == []
    )
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


def test_resolved_store_mismatch_fails_and_leaves_occurrence_unresolved(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    other_store_id = seed_store(db_conn, filename_store_token="999")
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    item = _normalized_item(
        store_id=other_store_id,  # deliberately disagrees with occurrence.store_id
        price="6.90",
        product_name="Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])

    assert (
        current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
        is None
    )
    assert (
        price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
        )
        == []
    )
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


def test_collected_at_mismatch_fails_and_leaves_occurrence_unresolved(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    item = _normalized_item(
        store_id=store_id,
        price="6.90",
        product_name="Name",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 1),  # genuinely unequal to occurrence's 6:00
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_occurrence(db_conn, occurrence_id=occ, products=(), normalized_items=[item])

    assert (
        current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
        is None
    )
    assert (
        price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
        )
        == []
    )
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


# --- J: whole-occurrence rollback includes normalized fields ----------------


def test_whole_occurrence_rollback_restores_normalized_fields(
    db_conn: pg8000.native.Connection,
) -> None:
    """Reuses the exact on_checkpoint failure-injection pattern already
    proven by test_activation_round2.py's
    test_multi_product_mid_activation_failure_rolls_back_every_product, with
    normalized_items in place of products.

    The "before_current_state" checkpoint at index 1 only ever fires after
    item 0's entire per-item body -- its CurrentState insert (with
    normalized facts) and its price_history insert -- has already executed
    in this same open transaction/connection (the per-item loop is strictly
    sequential: before_current_state(0) -> INSERT current_state(0) ->
    after_current_state(0) -> INSERT price_history(0) ->
    after_price_history(0) -> before_current_state(1)). The checkpoint
    callback below reads item 0's CurrentState row on the SAME connection
    before raising, observing the not-yet-committed write directly (same-
    transaction visibility), which distinguishes "a real normalized write
    executed, then rolled back" from "the checkpoint fired before any
    write happened"."""
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    item1 = _normalized_item(
        store_id=store_id,
        item_code_raw=ITEM_CODE_RAW,
        price="1.00",
        product_name="First",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(6, 0),
    )
    item2 = _normalized_item(
        store_id=store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price="2.00",
        product_name="Second",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 0),
    )

    def boom(name: str, index: int) -> None:
        if name == "before_current_state" and index == 1:
            # In-transaction observation, on the same connection, before
            # the injected exception rolls everything back: proves item
            # 0's normalized write genuinely happened, not merely that
            # the checkpoint fired before any write.
            in_flight_row = _normalized_current_state_row(
                db_conn, store_id=store_id, item_code_raw=ITEM_CODE_RAW
            )
            assert in_flight_row is not None
            assert in_flight_row["product_name"] == "First"
            assert in_flight_row["normalization_contract_version"] == 1

            raise RuntimeError("injected failure mid-occurrence")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn,
            occurrence_id=occ,
            products=(),
            normalized_items=[item1, item2],
            on_checkpoint=boom,
        )

    for code in (ITEM_CODE_RAW, ITEM_CODE_RAW_2):
        assert (
            current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code) is None
        )
        assert (
            price_history_for(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code)
            == []
        )
        assert _normalized_current_state_row(db_conn, store_id=store_id, item_code_raw=code) is None
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None
