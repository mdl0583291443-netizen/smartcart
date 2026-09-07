"""Round 2: price semantics, idempotency, and failure-injection/rollback
atomicity for activate_occurrence -- all provable on a single connection
(real Postgres transactions, no cross-connection concurrency needed). See
test_activation_concurrency.py for the ordering/stale/race tests that do
need multiple real connections.
"""

from __future__ import annotations

from decimal import Decimal

import pg8000.native
import pytest

from db_spike.round2_support import (
    CHAIN_ID,
    ITEM_CODE_RAW,
    ITEM_CODE_RAW_2,
    collected_at,
    make_occurrence,
    price,
    seed_products,
    seed_store,
)
from smartcart.db_spike.activation import (
    ActivationOutcome,
    activate_occurrence,
    activation_outcome,
    activation_status,
    current_state,
    price_history_for,
)


def test_identical_typed_decimal_price_creates_no_new_price_history_event(
    db_conn: pg8000.native.Connection,
) -> None:
    """7.0 and 7.00 are the same typed Decimal value: the second
    observation must update CurrentState (latest raw string, latest
    source occurrence) but must not append a second PriceHistory event
    solely because the source formatting changed."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ1 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    assert (
        activate_occurrence(db_conn, occurrence_id=occ1, products=[price("7.00")])
        == ActivationOutcome.APPLIED
    )

    occ2 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 5))
    assert (
        activate_occurrence(db_conn, occurrence_id=occ2, products=[price("7.0")])
        == ActivationOutcome.APPLIED
    )

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


def test_genuinely_different_typed_price_creates_a_new_price_history_event(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ1 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))
    activate_occurrence(db_conn, occurrence_id=occ1, products=[price("7.00")])

    occ2 = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 5))
    activate_occurrence(db_conn, occurrence_id=occ2, products=[price("6.50")])

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("7.00"), Decimal("6.50")]


def test_retry_after_fully_committed_activation_is_a_safe_noop(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    first = activate_occurrence(db_conn, occurrence_id=occ, products=[price("5.00")])
    assert first == ActivationOutcome.APPLIED
    assert activation_status(db_conn, occ) is not None
    assert activation_outcome(db_conn, occ) == "applied"

    second = activate_occurrence(db_conn, occurrence_id=occ, products=[price("5.00")])
    assert second == ActivationOutcome.ALREADY_APPLIED
    assert activation_outcome(db_conn, occ) == "applied"

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert len(history) == 1


def test_failure_before_any_derived_write_rolls_back_completely(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    def boom(name: str, index: int) -> None:
        if name == "before_current_state":
            raise RuntimeError("injected failure before any write")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn, occurrence_id=occ, products=[price("5.00")], on_checkpoint=boom
        )

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


def test_failure_after_current_state_before_price_history_rolls_back_both(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    def boom(name: str, index: int) -> None:
        if name == "after_current_state":
            raise RuntimeError("injected failure after CurrentState write")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn, occurrence_id=occ, products=[price("5.00")], on_checkpoint=boom
        )

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


def test_failure_after_price_history_before_completion_rolls_back_both(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    def boom(name: str, index: int) -> None:
        if name == "before_completion":
            raise RuntimeError("injected failure before activation completion")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn, occurrence_id=occ, products=[price("5.00")], on_checkpoint=boom
        )

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


def test_retry_after_rollback_succeeds_cleanly_with_no_duplicates(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    def boom(name: str, index: int) -> None:
        if name == "after_price_history":
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn, occurrence_id=occ, products=[price("5.00")], on_checkpoint=boom
        )

    outcome = activate_occurrence(db_conn, occurrence_id=occ, products=[price("5.00")])
    assert outcome == ActivationOutcome.APPLIED
    assert activation_outcome(db_conn, occ) == "applied"

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert len(history) == 1
    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("5.00")


def test_multi_product_activation_applies_all_products_atomically(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    outcome = activate_occurrence(
        db_conn,
        occurrence_id=occ,
        products=[
            price("1.00", item_code_raw=ITEM_CODE_RAW),
            price("2.00", item_code_raw=ITEM_CODE_RAW_2),
        ],
    )
    assert outcome == ActivationOutcome.APPLIED
    assert activation_outcome(db_conn, occ) == "applied"

    for code, expected in ((ITEM_CODE_RAW, "1.00"), (ITEM_CODE_RAW_2, "2.00")):
        state = current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code)
        assert state is not None
        assert state["current_price"] == Decimal(expected)


def test_multi_product_mid_activation_failure_rolls_back_every_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """One PriceFull occurrence with two products: inject a failure after
    the first product has already mutated CurrentState/PriceHistory
    in-transaction, but before the second product (and the occurrence
    itself) completes. Expected: ALL product effects roll back -- a
    per-product commit model is not acceptable."""
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    def boom(name: str, index: int) -> None:
        if name == "before_current_state" and index == 1:
            raise RuntimeError("injected failure mid-occurrence")

    with pytest.raises(RuntimeError, match="injected failure"):
        activate_occurrence(
            db_conn,
            occurrence_id=occ,
            products=[
                price("1.00", item_code_raw=ITEM_CODE_RAW),
                price("2.00", item_code_raw=ITEM_CODE_RAW_2),
            ],
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
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None

    retry_outcome = activate_occurrence(
        db_conn,
        occurrence_id=occ,
        products=[
            price("1.00", item_code_raw=ITEM_CODE_RAW),
            price("2.00", item_code_raw=ITEM_CODE_RAW_2),
        ],
    )
    assert retry_outcome == ActivationOutcome.APPLIED
    for code, expected in ((ITEM_CODE_RAW, "1.00"), (ITEM_CODE_RAW_2, "2.00")):
        state = current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code)
        assert state is not None
        assert state["current_price"] == Decimal(expected)
        history = price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code
        )
        assert len(history) == 1
    assert activation_outcome(db_conn, occ) == "applied"


def test_unresolved_occurrence_has_null_completed_at_and_null_outcome(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


def test_database_check_constraint_rejects_outcome_without_completion_timestamp(
    db_conn: pg8000.native.Connection,
) -> None:
    """The activation_completed_at/activation_outcome pair must be both-
    null or both-set; migration 0003's CHECK constraint makes the
    inconsistent combination unrepresentable, not just unintended by
    application code."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(6, 0))

    with pytest.raises(pg8000.native.DatabaseError):
        db_conn.run(
            "UPDATE artifact_occurrence SET activation_outcome = 'applied' "
            "WHERE occurrence_id = :occurrence_id",
            occurrence_id=occ,
        )
