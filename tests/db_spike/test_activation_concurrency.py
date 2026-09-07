"""Round 2's required concurrency tests, exercised against real PostgreSQL
(pgserver) transaction/locking semantics -- multiple genuine connections
and, where the invariant is specifically about worker interleaving, real
threads. No Python-side lock/mutex is used to force an ordering the
database itself would not otherwise produce; where threads are used, they
only schedule when each worker *attempts* activation -- all serialization
proven here comes from the Store row FOR UPDATE lock and the ordering/
idempotency queries inside activate_occurrence, not from test-side
coordination.
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal

import pg8000.native

from db_spike.round2_support import (
    CHAIN_ID,
    ITEM_CODE_RAW,
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
from smartcart.db_spike.db import connect


def test_normal_ordered_activation_produces_expected_history_sequence(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ_initial = make_occurrence(
        db_conn, store_id=store_id, collected_at_value=collected_at(11, 0)
    )
    occ_a = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 0))
    occ_b = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 5))

    assert (
        activate_occurrence(db_conn, occurrence_id=occ_initial, products=[price("10.00")])
        == ActivationOutcome.APPLIED
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ_a, products=[price("8.00")])
        == ActivationOutcome.APPLIED
    )
    assert (
        activate_occurrence(db_conn, occurrence_id=occ_b, products=[price("7.00")])
        == ActivationOutcome.APPLIED
    )

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("10.00"), Decimal("8.00"), Decimal("7.00")]


def test_later_ordered_worker_starting_first_does_not_overtake_earlier_unresolved_occurrence(
    db_conn: pg8000.native.Connection, db_dsn: str
) -> None:
    """B and A are both already durably registered before either worker
    attempts activation. B's worker begins first. B must not overtake A:
    B is deferred until A (the earlier-ordered, still-unresolved
    occurrence) has activated."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ_initial = make_occurrence(
        db_conn, store_id=store_id, collected_at_value=collected_at(11, 0)
    )
    activate_occurrence(db_conn, occurrence_id=occ_initial, products=[price("10.00")])

    occ_a = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 0))
    occ_b = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 5))

    result: dict[str, ActivationOutcome] = {}

    def worker_b() -> None:
        conn = connect(db_dsn)
        try:
            result["b_first_attempt"] = activate_occurrence(
                conn, occurrence_id=occ_b, products=[price("7.00")]
            )
        finally:
            conn.close()

    thread_b = threading.Thread(target=worker_b)
    thread_b.start()
    thread_b.join(timeout=10)

    assert result["b_first_attempt"] == ActivationOutcome.DEFERRED
    assert activation_status(db_conn, occ_b) is None
    assert activation_outcome(db_conn, occ_b) is None
    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("10.00")
    history_after_deferred = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history_after_deferred] == [Decimal("10.00")]

    conn_a = connect(db_dsn)
    try:
        outcome_a = activate_occurrence(conn_a, occurrence_id=occ_a, products=[price("8.00")])
    finally:
        conn_a.close()
    assert outcome_a == ActivationOutcome.APPLIED

    conn_b_retry = connect(db_dsn)
    try:
        outcome_b_retry = activate_occurrence(
            conn_b_retry, occurrence_id=occ_b, products=[price("7.00")]
        )
    finally:
        conn_b_retry.close()
    assert outcome_b_retry == ActivationOutcome.APPLIED

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("10.00"), Decimal("8.00"), Decimal("7.00")]


def test_two_workers_racing_to_activate_the_same_occurrence_apply_effects_exactly_once(
    db_conn: pg8000.native.Connection, db_dsn: str
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 0))

    barrier = threading.Barrier(2)
    outcomes: list[ActivationOutcome | None] = [None, None]

    def worker(index: int) -> None:
        conn = connect(db_dsn)
        try:
            barrier.wait(timeout=10)
            outcomes[index] = activate_occurrence(conn, occurrence_id=occ, products=[price("9.00")])
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert outcomes.count(ActivationOutcome.APPLIED) == 1
    assert outcomes.count(ActivationOutcome.ALREADY_APPLIED) == 1

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert len(history) == 1
    assert history[0]["price"] == Decimal("9.00")


def test_different_stores_activate_concurrently_without_cross_store_blocking(
    db_conn: pg8000.native.Connection, db_dsn: str
) -> None:
    """Store A's transaction holds its Store row lock (paused mid-
    activation via the test-only checkpoint hook) while Store B's
    activation, on a separate connection, runs to completion. If the
    mechanism serialized across stores (e.g. a global lock), B would block
    until A releases; it must not."""
    store_a = seed_store(db_conn, filename_store_token="store-a")
    store_b = seed_store(db_conn, filename_store_token="store-b")
    seed_products(db_conn)

    occ_a = make_occurrence(db_conn, store_id=store_a, collected_at_value=collected_at(12, 0))
    occ_b = make_occurrence(db_conn, store_id=store_b, collected_at_value=collected_at(12, 0))

    holding = threading.Event()
    release = threading.Event()

    def pause_a(name: str, index: int) -> None:
        if name == "before_completion":
            holding.set()
            release.wait(timeout=10)

    def worker_a() -> None:
        conn = connect(db_dsn)
        try:
            activate_occurrence(
                conn, occurrence_id=occ_a, products=[price("1.00")], on_checkpoint=pause_a
            )
        finally:
            conn.close()

    thread_a = threading.Thread(target=worker_a)
    thread_a.start()
    assert holding.wait(timeout=10), "Store A's worker never reached its held checkpoint"

    conn_b = connect(db_dsn)
    started = time.monotonic()
    try:
        outcome_b = activate_occurrence(conn_b, occurrence_id=occ_b, products=[price("2.00")])
    finally:
        conn_b.close()
    elapsed = time.monotonic() - started

    release.set()
    thread_a.join(timeout=10)

    assert outcome_b == ActivationOutcome.APPLIED
    assert elapsed < 2.0, (
        f"Store B's activation took {elapsed:.2f}s while Store A held its own store lock -- "
        "this indicates unwanted cross-store serialization."
    )


def test_same_collected_at_ties_break_deterministically_by_occurrence_id(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    same_time = collected_at(12, 0)

    occ_lower_id = make_occurrence(db_conn, store_id=store_id, collected_at_value=same_time)
    occ_higher_id = make_occurrence(db_conn, store_id=store_id, collected_at_value=same_time)
    assert occ_higher_id > occ_lower_id

    outcome_higher_first = activate_occurrence(
        db_conn, occurrence_id=occ_higher_id, products=[price("4.00")]
    )
    assert outcome_higher_first == ActivationOutcome.DEFERRED

    outcome_lower = activate_occurrence(
        db_conn, occurrence_id=occ_lower_id, products=[price("3.00")]
    )
    assert outcome_lower == ActivationOutcome.APPLIED

    outcome_higher_retry = activate_occurrence(
        db_conn, occurrence_id=occ_higher_id, products=[price("4.00")]
    )
    assert outcome_higher_retry == ActivationOutcome.APPLIED

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("3.00"), Decimal("4.00")]


def test_stale_occurrence_is_preserved_without_mutating_derived_state(
    db_conn: pg8000.native.Connection,
) -> None:
    """A newer occurrence commits first; only afterward does an older
    (by collected_at) occurrence become durable. The older occurrence must
    be preserved (marked resolved) but must never mutate CurrentState or
    PriceHistory."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    occ_new = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 10))
    outcome_new = activate_occurrence(db_conn, occurrence_id=occ_new, products=[price("5.00")])
    assert outcome_new == ActivationOutcome.APPLIED
    assert activation_outcome(db_conn, occ_new) == "applied"

    occ_old = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 0))
    outcome_old = activate_occurrence(db_conn, occurrence_id=occ_old, products=[price("8.00")])
    assert outcome_old == ActivationOutcome.STALE_PRESERVED
    assert activation_status(db_conn, occ_old) is not None
    assert activation_outcome(db_conn, occ_old) == "stale_preserved"

    state = current_state(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert state is not None
    assert state["current_price"] == Decimal("5.00")
    assert state["source_occurrence_id"] == occ_new

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert [h["price"] for h in history] == [Decimal("5.00")]
