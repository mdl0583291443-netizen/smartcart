"""RED tests for the proposed normalize-to-persistence integration seam
(Normalize -> Persistence Pipeline Integration slice).

This module does not exist yet:

    from smartcart.integration.occurrence_activation import (
        StoreResolutionContext,
        activate_normalized_occurrence,
    )

That import is a TEST-SIDE PROPOSAL only, chosen as the smallest reasonable
shape to express the frozen behavioral invariants (I1-I7) -- it is not a
frozen production API and not permission to implement it. This file is
expected to fail at collection (ModuleNotFoundError) until the seam exists.

Frozen architecture this file tests against:

    StoreResolutionContext(
        occurrence_id: int, subchain_id: str, source: str, alias_context: str,
    )

    activate_normalized_occurrence(
        conn, *, context: StoreResolutionContext,
        items: Sequence[NormalizedPriceItem],
        on_checkpoint: Callable[[str, int], None] | None = None,
    ) -> ActivationOutcome

The seam is occurrence/batch scoped, receives already-normalized
`NormalizedPriceItem`s (never calls retailer-specific normalize_* itself),
resolves the store exactly once per batch via the existing, unchanged
`catalog.get_or_create_store_by_alias`, maps every item losslessly into a
`NormalizedActivationItem`, and delegates the entire mapped batch to the
existing, unchanged `activate_occurrence` in one call
(`products=[]`, `normalized_items=<mapped batch>`). `chain_id`, raw
`store_id`, and `collected_at` are deliberately NOT part of the context --
they are read from the `NormalizedPriceItem`s themselves; the context only
carries the conceptual facts a `NormalizedPriceItem` cannot supply:
`occurrence_id`, `subchain_id`, `source`, `alias_context`.

`on_checkpoint` is a diagnostic/testing-oriented optional strict
pass-through: the seam must not interpret, transform, store, or invoke it
itself, and must not use it for its own control flow -- it is forwarded
verbatim to `activate_occurrence(..., on_checkpoint=on_checkpoint)`.

Reuses tests/db_spike/round2_support.py's existing seeding helpers
unmodified, exactly as test_activation_normalized.py already does, per
constraint 4 (reuse existing db_spike fixtures/setup/query patterns).

Per constraint 1: no test here uses a normalize_item() failure as an
integration-layer failure case -- this layer only ever receives
already-normalized items, so normalize.* is never invoked or imported here.

Per constraint 2: no "unresolvable raw store ID" validation is assumed --
get_or_create_store_by_alias has no such validation (see the repository
inspection this test file is based on), so no test here exercises it.
"""

from __future__ import annotations

import threading
import time
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
    activation_outcome,
    activation_status,
    current_state,
    price_history_for,
)
from smartcart.db_spike.catalog import store_source_aliases
from smartcart.db_spike.db import connect
from smartcart.db_spike.normalized_evidence import normalized_evidence_for_occurrence
from smartcart.integration.occurrence_activation import (
    StoreResolutionContext,
    activate_normalized_occurrence,
)
from smartcart.normalize.contract import NormalizedPriceItem

# Matches round2_support.seed_store's default filename_store_token, and is
# the raw retailer store id every NormalizedPriceItem below carries.
_RAW_STORE_ID = "413"
_SOURCE = "shufersal"
_ALIAS_CONTEXT = "filename_store_id"


def _price_item(
    *,
    chain_id: str = CHAIN_ID,
    store_id: str = _RAW_STORE_ID,
    item_code_raw: str = ITEM_CODE_RAW,
    price: str,
    price_raw: str | None = None,
    product_name: str,
    declared_quantity: str,
    declared_quantity_raw: str | None = None,
    declared_quantity_unit_raw: str,
    is_weighted: bool | None,
    collected_at_value: datetime,
) -> NormalizedPriceItem:
    return NormalizedPriceItem(
        retailer_chain_id=chain_id,
        retailer_item_id=item_code_raw,
        store_id=store_id,
        published_price=Decimal(price),
        published_price_raw=price_raw if price_raw is not None else price,
        declared_quantity=Decimal(declared_quantity),
        declared_quantity_raw=(
            declared_quantity_raw if declared_quantity_raw is not None else declared_quantity
        ),
        declared_quantity_unit_raw=declared_quantity_unit_raw,
        is_weighted=is_weighted,
        product_name=product_name,
        collected_at=collected_at_value,
    )


def _context(occurrence_id: int) -> StoreResolutionContext:
    return StoreResolutionContext(
        occurrence_id=occurrence_id,
        subchain_id=SUBCHAIN_ID,
        source=_SOURCE,
        alias_context=_ALIAS_CONTEXT,
    )


def _store_count(conn: pg8000.native.Connection, *, chain_id: str) -> int:
    rows = conn.run("SELECT count(*) FROM store WHERE chain_id = :chain_id", chain_id=chain_id)
    count: int = rows[0][0]
    return count


def _alias_count(conn: pg8000.native.Connection, *, chain_id: str) -> int:
    rows = conn.run(
        "SELECT count(*) FROM store_source_alias WHERE chain_id = :chain_id", chain_id=chain_id
    )
    count: int = rows[0][0]
    return count


def _alias_exists(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    source: str,
    alias_context: str,
    raw_value: str,
) -> bool:
    """Positive existence check for one specific alias identity tuple --
    used to prove a *particular* candidate identity was never created,
    which a chain-wide count alone does not pin down as precisely."""
    rows = conn.run(
        """
        SELECT 1 FROM store_source_alias
        WHERE chain_id = :chain_id AND source = :source
          AND alias_context = :alias_context AND raw_value = :raw_value
        """,
        chain_id=chain_id,
        source=source,
        alias_context=alias_context,
        raw_value=raw_value,
    )
    return bool(rows)


def _current_state_row(
    conn: pg8000.native.Connection, *, item_code_raw: str, chain_id: str = CHAIN_ID
) -> dict[str, object] | None:
    rows = conn.run(
        """
        SELECT product_name, declared_quantity, declared_quantity_raw,
               declared_quantity_unit_raw, is_weighted, normalization_contract_version,
               store_id
        FROM store_product_current_state
        WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw
        """,
        chain_id=chain_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    columns = (
        "product_name",
        "declared_quantity",
        "declared_quantity_raw",
        "declared_quantity_unit_raw",
        "is_weighted",
        "normalization_contract_version",
        "store_id",
    )
    return dict(zip(columns, rows[0], strict=True))


# --- T1: real occurrence happy path / exhaustive seam -----------------------


def test_t1_real_occurrence_happy_path_exhaustive_seam(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    item1 = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="6.90",
        product_name="חלב טרי 3% תנובה 1 ליטר",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    item2 = _price_item(
        item_code_raw=ITEM_CODE_RAW_2,
        price="12.50",
        product_name="קוקה קולה 1.5 ליטר",
        declared_quantity="1.5",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )

    outcome = activate_normalized_occurrence(db_conn, context=_context(occ), items=[item1, item2])
    assert outcome == ActivationOutcome.APPLIED

    for item, code in ((item1, ITEM_CODE_RAW), (item2, ITEM_CODE_RAW_2)):
        state = current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code)
        assert state is not None
        assert state["current_price"] == item.published_price
        assert state["current_price_raw"] == item.published_price_raw
        assert state["source_occurrence_id"] == occ

        history = price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=code
        )
        assert len(history) == 1
        assert history[0]["price"] == item.published_price
        assert history[0]["price_raw"] == item.published_price_raw

        row = _current_state_row(db_conn, item_code_raw=code)
        assert row is not None
        assert row["product_name"] == item.product_name
        assert row["declared_quantity"] == item.declared_quantity
        assert row["declared_quantity_raw"] == item.declared_quantity_raw
        assert row["declared_quantity_unit_raw"] == item.declared_quantity_unit_raw
        assert row["is_weighted"] == item.is_weighted
        assert row["normalization_contract_version"] == 1
        assert row["store_id"] == store_id


# --- T2: one occurrence maps to exactly one catalog Store/alias identity ----


def test_t2_occurrence_maps_to_exactly_one_catalog_store_identity(
    db_conn: pg8000.native.Connection,
) -> None:
    """Downgraded claim (per RED review): get_or_create_store_by_alias is
    idempotent (repository evidence: same (chain_id, source, alias_context,
    raw_value) tuple always returns the same store_id, first-seen-only
    creates a row), so "exactly one Store/alias row exists afterward" is
    consistent with both "resolved once" and "resolved once per item with
    identical inputs" -- it does NOT distinguish call count. No production
    instrumentation (audit columns, counters, timestamps) exists to make
    call count directly observable, and none is invented here to force it.

    What this test DOES positively prove, by querying real catalog state:
    one occurrence, carrying multiple items that share one raw store_id,
    ends up mapped to exactly one Store identity and exactly one alias
    identity in the catalog -- and every item in the batch is persisted
    against that same resolved store, not some other/duplicate one.
    """
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    item1 = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="1.00",
        product_name="First",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    item2 = _price_item(
        item_code_raw=ITEM_CODE_RAW_2,
        price="2.00",
        product_name="Second",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=when,
    )

    outcome = activate_normalized_occurrence(db_conn, context=_context(occ), items=[item1, item2])
    assert outcome == ActivationOutcome.APPLIED

    # Exactly one relevant Store identity, exactly one relevant alias
    # identity, chain-wide (not just "at least one" / "not duplicated").
    assert _store_count(db_conn, chain_id=CHAIN_ID) == 1
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == 1
    aliases = store_source_aliases(db_conn, store_id=store_id)
    matching = [a for a in aliases if a == (_SOURCE, _ALIAS_CONTEXT, _RAW_STORE_ID)]
    assert len(matching) == 1

    # All batch items persist against that same resolved store -- not a
    # per-item or drifted store identity.
    for code in (ITEM_CODE_RAW, ITEM_CODE_RAW_2):
        row = _current_state_row(db_conn, item_code_raw=code)
        assert row is not None
        assert row["store_id"] == store_id


# --- T3: mixed raw store IDs rejected pre-resolution -------------------------


def test_t3_mixed_raw_store_ids_rejected_before_resolution(
    db_conn: pg8000.native.Connection,
) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    baseline_stores = _store_count(db_conn, chain_id=CHAIN_ID)
    baseline_aliases = _alias_count(db_conn, chain_id=CHAIN_ID)

    item1 = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        store_id=_RAW_STORE_ID,
        price="1.00",
        product_name="First",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    item2 = _price_item(
        item_code_raw=ITEM_CODE_RAW_2,
        store_id="999",  # deliberately disagrees with item1's raw store_id
        price="2.00",
        product_name="Second",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=when,
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_normalized_occurrence(db_conn, context=_context(occ), items=[item1, item2])

    # Chain-wide baseline is unchanged (no side effect of any kind)...
    assert _store_count(db_conn, chain_id=CHAIN_ID) == baseline_stores
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == baseline_aliases
    # ...and, specifically, no alias was ever created for the mismatched
    # second raw store_id -- the one concrete new identity a buggy
    # resolve-before-agreement-check implementation could have created.
    assert not _alias_exists(
        db_conn, chain_id=CHAIN_ID, source=_SOURCE, alias_context=_ALIAS_CONTEXT, raw_value="999"
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


# --- T4: mixed retailer_chain_id rejected pre-resolution ---------------------


def test_t4_mixed_chain_id_rejected_before_resolution(db_conn: pg8000.native.Connection) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    baseline_stores = _store_count(db_conn, chain_id=CHAIN_ID)
    baseline_aliases = _alias_count(db_conn, chain_id=CHAIN_ID)

    item1 = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        chain_id=CHAIN_ID,
        price="1.00",
        product_name="First",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    item2 = _price_item(
        item_code_raw=ITEM_CODE_RAW_2,
        chain_id="0000000000000",  # deliberately disagrees with item1's chain_id
        price="2.00",
        product_name="Second",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=when,
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_normalized_occurrence(db_conn, context=_context(occ), items=[item1, item2])

    # Chain-wide baseline for the real chain is unchanged...
    assert _store_count(db_conn, chain_id=CHAIN_ID) == baseline_stores
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == baseline_aliases
    # ...and, specifically, no store was ever created under the mismatched
    # second chain_id -- the one concrete new identity a buggy
    # resolve-before-agreement-check implementation could have created.
    assert _store_count(db_conn, chain_id="0000000000000") == 0
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


# --- T5: mixed collected_at rejected pre-resolution --------------------------


def test_t5_mixed_collected_at_rejected_before_resolution(
    db_conn: pg8000.native.Connection,
) -> None:
    """Both items here share the same chain_id and raw store_id -- only
    collected_at differs -- so, unlike T3/T4, there is no distinct candidate
    identity (no new raw store_id, no new chain_id) a buggy implementation
    could have created; the shared identity already exists from setup
    (seed_store), so the catalog count-unchanged assertions below hold
    trivially regardless of whether resolution was attempted at all (the
    same idempotency limitation noted on T2 -- catalog counts alone cannot
    be non-vacuous here). The non-vacuous proof for THIS mismatch is the
    CurrentState/price_history/activation_status assertions: they show the
    rejection happened before any activation effect, which is the concrete
    claim this test is actually able to establish for a collected_at-only
    mismatch."""
    store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    baseline_stores = _store_count(db_conn, chain_id=CHAIN_ID)
    baseline_aliases = _alias_count(db_conn, chain_id=CHAIN_ID)

    item1 = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="1.00",
        product_name="First",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    item2 = _price_item(
        item_code_raw=ITEM_CODE_RAW_2,
        price="2.00",
        product_name="Second",
        declared_quantity="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at_value=collected_at(6, 1),  # genuinely unequal to item1's 6:00
    )

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_normalized_occurrence(db_conn, context=_context(occ), items=[item1, item2])

    assert _store_count(db_conn, chain_id=CHAIN_ID) == baseline_stores
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == baseline_aliases
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


# --- T6: empty normalized batch rejected before side effects -----------------


def test_t6_empty_batch_rejected_before_side_effects(db_conn: pg8000.native.Connection) -> None:
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    baseline_stores = _store_count(db_conn, chain_id=CHAIN_ID)
    baseline_aliases = _alias_count(db_conn, chain_id=CHAIN_ID)

    with pytest.raises(Exception):  # noqa: B017 -- exact type not yet contractually established
        activate_normalized_occurrence(db_conn, context=_context(occ), items=[])

    assert _store_count(db_conn, chain_id=CHAIN_ID) == baseline_stores
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == baseline_aliases
    assert (
        current_state(db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW)
        is None
    )
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


# --- T7: on_checkpoint pass-through (1st call) + ALREADY_APPLIED retry (2nd) -


def test_t7_on_checkpoint_pass_through_then_already_applied_retry(
    db_conn: pg8000.native.Connection,
) -> None:
    """T7 proves two separate, narrower things -- not one combined "genuine
    retry re-entry" claim:

    1. FIRST call: on_checkpoint is a strict pass-through into the real
       activate_occurrence engine. Reuses the existing "before_completion"
       checkpoint already proven by Slice 2 (test_activation_round2.py,
       test_activation_concurrency.py) -- it fires exactly once, at index
       -1, after all products in the occurrence have been written, right
       before the occurrence is marked resolved. Observing it fire during
       the integration seam's call is direct evidence the seam forwards
       the callback verbatim into the real engine rather than
       intercepting, transforming, storing, or invoking it independently
       -- no new checkpoint name or mechanism is introduced.

    2. SECOND call (retry, same occurrence/context/items, no on_checkpoint
       supplied): the existing activate_occurrence engine alone decides
       ALREADY_APPLIED -- no new price_history row, and CurrentState is
       byte-for-byte unchanged from what the first call already produced.

    Acknowledged limitation, stated honestly rather than papered over: this
    does NOT prove the retry call dynamically re-enters activate_occurrence
    mid-flight. Per activation.py's own control flow, its ALREADY_APPLIED
    branch returns immediately -- before the per-item loop that owns every
    on_checkpoint call site -- so ALREADY_APPLIED intentionally never fires
    a checkpoint, by existing, frozen, unmodified design (not a gap in this
    test, and activate_occurrence itself must not be changed to add one).
    No checkpoint is asserted on the second call for exactly this reason.
    That activate_normalized_occurrence contains no independent
    idempotency/retry short-circuit of its own -- i.e. that ALREADY_APPLIED
    here is genuinely activate_occurrence's decision, not a competing
    integration-layer one that happens to return the same enum value -- is
    a static property of the implementation this on_checkpoint contract
    cannot dynamically observe; it is left to be verified at implementation
    code review, not asserted here."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    item = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="6.90",
        product_name="Original",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )

    checkpoints_seen: list[tuple[str, int]] = []

    def record_checkpoint(name: str, index: int) -> None:
        checkpoints_seen.append((name, index))

    first_outcome = activate_normalized_occurrence(
        db_conn, context=_context(occ), items=[item], on_checkpoint=record_checkpoint
    )
    assert first_outcome == ActivationOutcome.APPLIED
    assert ("before_completion", -1) in checkpoints_seen

    state_after_first = _current_state_row(db_conn, item_code_raw=ITEM_CODE_RAW)
    assert state_after_first is not None

    second_outcome = activate_normalized_occurrence(db_conn, context=_context(occ), items=[item])
    assert second_outcome == ActivationOutcome.ALREADY_APPLIED

    history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert len(history) == 1

    state_after_second = _current_state_row(db_conn, item_code_raw=ITEM_CODE_RAW)
    assert state_after_second == state_after_first


# --- T8: real downstream FK failure propagates unswallowed (invariant 7) ----


def test_t8_store_resolution_fk_violation_propagates_as_database_error(
    db_conn: pg8000.native.Connection,
) -> None:
    """Invariant 7: "the integration layer must not generically catch,
    swallow, or reclassify exceptions from its downstream operations."

    Scenario, built entirely from real, unmodified repository state -- no
    corrupted database, no disabled constraints, no monkeypatching/mocking,
    no dependency injection, no invented exception:

    - CHAIN_ID is registered (via seed_store's own upsert_chain), and a
      real, valid, unrelated Store already exists for it under the real
      SUBCHAIN_ID -- exactly like every other test in this file.
    - context.subchain_id below is "999", a subchain that was never
      registered (no upsert_subchain call for (CHAIN_ID, "999") anywhere
      in this test), and the item's raw store_id is "777", a raw value
      never previously resolved for (CHAIN_ID, "shufersal",
      "filename_store_id", ...) -- so the alias lookup inside
      get_or_create_store_by_alias is a genuine miss, forcing it down its
      real `INSERT INTO store (chain_id, subchain_id, ...)` path (catalog.py).
    - That INSERT hits the real, existing schema constraint
      `store(chain_id, subchain_id) REFERENCES subchain(chain_id,
      subchain_id)` (migrations/0001_initial_schema.sql) -- Postgres itself
      rejects it, deterministically, every time, as SQLSTATE 23503
      (foreign_key_violation), raised by pg8000 as
      pg8000.native.DatabaseError. This exact class/assertion technique is
      already established in this suite (test_activation_round2.py's
      pytest.raises(pg8000.native.DatabaseError), and
      test_store_product_current_state_normalized_columns.py's SQLSTATE
      pinning via exc_info.value.args[0]["C"]) -- not invented here.

    Why zero side effects are expected: get_or_create_store_by_alias runs
    its own INSERT inside its own `transaction(conn)` (catalog.py), whose
    bare `except BaseException: rollback; raise` guarantees the failed
    INSERT is rolled back, not partially applied. Per the frozen
    architecture (store resolution happens once, before activation, in
    its own separate transaction from activate_occurrence), this failure
    occurs entirely within store resolution -- activate_occurrence is
    never reached, so the occurrence must remain completely untouched.

    What T8 proves: this real downstream infrastructure/database failure
    propagates through the integration seam exactly as
    pg8000.native.DatabaseError / SQLSTATE 23503 -- not swallowed, not
    wrapped, not reclassified into some source-data-fault-shaped exception
    -- and leaves no persisted store-resolution or activation effect.

    What T8 does NOT prove: exception propagation for every possible
    downstream exception class or code path (e.g. Candidates 2/3 from the
    invariant-7 inspection -- an activate_occurrence ValueError guard --
    are separate, unproven-here scenarios; T1-T7 already cover the
    seam's own pre-resolution ValueError-shaped rejections, which are a
    different invariant, I2, not this one)."""
    store_id = seed_store(db_conn)
    seed_products(db_conn)
    when = collected_at(6, 0)
    occ = make_occurrence(db_conn, store_id=store_id, collected_at_value=when)

    never_registered_subchain = "999"
    never_resolved_raw_store_id = "777"

    baseline_stores = _store_count(db_conn, chain_id=CHAIN_ID)
    baseline_aliases = _alias_count(db_conn, chain_id=CHAIN_ID)
    assert not _alias_exists(
        db_conn,
        chain_id=CHAIN_ID,
        source=_SOURCE,
        alias_context=_ALIAS_CONTEXT,
        raw_value=never_resolved_raw_store_id,
    )

    item = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        store_id=never_resolved_raw_store_id,
        price="6.90",
        product_name="Original",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=when,
    )
    context = StoreResolutionContext(
        occurrence_id=occ,
        subchain_id=never_registered_subchain,
        source=_SOURCE,
        alias_context=_ALIAS_CONTEXT,
    )

    with pytest.raises(pg8000.native.DatabaseError) as exc_info:
        activate_normalized_occurrence(db_conn, context=context, items=[item])

    assert exc_info.value.args[0]["C"] == "23503"  # foreign_key_violation

    # 1/2: no new Store or StoreAlias row from the failed resolution.
    assert _store_count(db_conn, chain_id=CHAIN_ID) == baseline_stores
    assert _alias_count(db_conn, chain_id=CHAIN_ID) == baseline_aliases
    assert not _alias_exists(
        db_conn,
        chain_id=CHAIN_ID,
        source=_SOURCE,
        alias_context=_ALIAS_CONTEXT,
        raw_value=never_resolved_raw_store_id,
    )

    # 3/4: no CurrentState/price_history effect -- activate_occurrence was
    # never reached.
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

    # 5: the occurrence itself remains completely unresolved.
    assert activation_status(db_conn, occ) is None
    assert activation_outcome(db_conn, occ) is None


# --- RED-2: durable normalized evidence before and surviving a real DEFERRED

_BLOCKER_LOCK_TIMEOUT_S = 3.0
_JOIN_TIMEOUT_S = 10.0


def test_red2_normalized_evidence_committed_before_and_surviving_real_deferred(
    db_conn: pg8000.native.Connection, db_dsn: str
) -> None:
    """RED-2 (T13 Slice A). Requirement (frozen architecture): the future
    `activate_normalized_occurrence()` orchestration must, in this order,
    (1) resolve the store, (2) build `NormalizedActivationItem`s, (3)
    durably persist normalized occurrence evidence in its OWN committed
    transaction, and only then (4) attempt `activate_occurrence()` in a
    later transaction. Evidence committed in step 3 must remain durable and
    unchanged even when step 4 defers (`ActivationOutcome.DEFERRED`) --
    evidence persistence must not depend on, or be undone by, activation's
    own outcome.

    Scenario (the normalized equivalent of the established Round 2 A/B
    ordering scenario, e.g.
    test_activation_concurrency.py::test_later_ordered_worker_starting_first_does_not_overtake_earlier_unresolved_occurrence):
    a baseline occurrence for this store is already applied
    (CurrentState/PriceHistory exist); occurrence A is a later, still-
    unresolved occurrence for the same store; occurrence B is later still.
    B's worker genuinely attempts `activate_normalized_occurrence()` while
    A remains unresolved, so B's real activation decision must be
    `DEFERRED` -- never mocked, never asserted without actually reaching
    that decision.

    Temporal observation uses three genuine, separate connections (plus
    `db_conn` for setup/baseline readback), exactly per the frozen
    constraints: no test hook is added to production code, no direct call
    to `persist_normalized_occurrence_evidence()`, no nested transactions,
    activation is never mocked or bypassed.

    - A BLOCKER connection opens its own transaction and takes
      `SELECT store_id FROM store WHERE store_id = :store_id FOR KEY SHARE`
      on B's already-resolved store row (the store/alias already exist,
      seeded before the blocker's lock is taken). Per real PostgreSQL
      row-lock semantics (see this engagement's T13 RED-2 lock-barrier
      recon): `FOR KEY SHARE` does not conflict with the plain read
      `get_or_create_store_by_alias` performs on its existing-alias path,
      nor with the `FOR KEY SHARE` a foreign-key check acquires on the
      referenced `store` row when `normalized_occurrence_evidence` rows
      are inserted -- so store resolution and evidence insertion/commit
      can both complete while this lock is held. It DOES conflict with
      `activate_occurrence()`'s own
      `SELECT store_id FROM store WHERE store_id = :store_id FOR UPDATE`
      (src/smartcart/db_spike/activation.py), so that statement -- and
      therefore B's entire DEFERRED decision, which is made after
      acquiring that lock -- is forced to wait.
    - A WORKER connection runs the real `activate_normalized_occurrence()`
      for B, on its own thread.
    - An OBSERVER connection polls, with a bounded timeout, for B's
      `normalized_occurrence_evidence` rows to become visible -- via
      read-only SQL (`evidence_id` values) and via the real production
      readback helper (`normalized_evidence_for_occurrence`) -- entirely
      while the blocker lock is still held and B's worker is still
      genuinely blocked (proven by `thread.is_alive()`), i.e. strictly
      before B's real DEFERRED decision is even reached.

    EXPECTED RED (today): the observer's bounded wait for B's evidence
    times out and finds zero rows. This is NOT a timing flake and not a
    lock-semantics problem -- `activate_normalized_occurrence()`
    (src/smartcart/integration/occurrence_activation.py) currently does
    nothing but resolve the store and call `activate_occurrence()`; it
    never calls `persist_normalized_occurrence_evidence()` at all, so no
    row is ever written to `normalized_occurrence_evidence` by any
    production path, regardless of how long the observer waits or how the
    blocker lock is held. The RED is attributable exactly to that missing
    production wiring, not to test mechanics.

    Once evidence persistence is wired into `activate_normalized_occurrence`
    per the frozen architecture, this test additionally proves (after the
    blocker lock is released): B's worker completes with exactly
    `ActivationOutcome.DEFERRED`; the same ordered `evidence_id` values and
    the same semantic evidence observed while the lock was held remain,
    unchanged and un-duplicated; B stays unresolved; and CurrentState/
    PriceHistory remain exactly at the pre-existing baseline.

    Cleanup is safe by construction: the blocker's lock is released and the
    worker thread is joined in a `finally` block that runs whether or not
    the RED assertion above succeeds, and every extra connection opened by
    this test is closed in an outer `finally` -- no hang, no leaked
    connection or thread, regardless of where this test fails.
    """
    store_id = seed_store(db_conn)
    seed_products(db_conn)

    # Baseline: an already-applied occurrence gives CurrentState/PriceHistory
    # a real prior value this test proves B's deferred attempt must not
    # disturb.
    occ_initial = make_occurrence(
        db_conn, store_id=store_id, collected_at_value=collected_at(11, 0)
    )
    baseline_item = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="10.00",
        product_name="Baseline",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(11, 0),
    )
    baseline_outcome = activate_normalized_occurrence(
        db_conn, context=_context(occ_initial), items=[baseline_item]
    )
    assert baseline_outcome == ActivationOutcome.APPLIED

    baseline_current_state = _current_state_row(db_conn, item_code_raw=ITEM_CODE_RAW)
    baseline_history = price_history_for(
        db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
    )
    assert baseline_current_state is not None
    assert len(baseline_history) == 1

    # A: later than the baseline, earlier than B, deliberately never
    # activated -- stays unresolved for the whole test, exactly like the
    # established A/B ordering scenario.
    occ_a = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 0))
    # B: later than A. Store and alias already exist (seeded above) before
    # the blocker takes its lock.
    occ_b = make_occurrence(db_conn, store_id=store_id, collected_at_value=collected_at(12, 5))

    item_b = _price_item(
        item_code_raw=ITEM_CODE_RAW,
        price="7.00",
        product_name="B Item",
        declared_quantity="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at_value=collected_at(12, 5),
    )

    conn_blocker = connect(db_dsn)
    conn_worker = connect(db_dsn)
    conn_observer = connect(db_dsn)

    worker_result: dict[str, object] = {}

    def run_worker() -> None:
        try:
            worker_result["outcome"] = activate_normalized_occurrence(
                conn_worker, context=_context(occ_b), items=[item_b]
            )
        except BaseException as exc:  # noqa: BLE001 -- captured for the main thread to report
            worker_result["error"] = exc

    thread = threading.Thread(target=run_worker)
    thread_started = False
    evidence_ids_while_held: list[int] = []

    try:
        try:
            conn_blocker.run("begin")
            conn_blocker.run(
                "SELECT store_id FROM store WHERE store_id = :store_id FOR KEY SHARE",
                store_id=store_id,
            )

            thread.start()
            thread_started = True

            deadline = time.monotonic() + _BLOCKER_LOCK_TIMEOUT_S
            semantic_while_held = None
            while time.monotonic() < deadline:
                rows = conn_observer.run(
                    "SELECT evidence_id FROM normalized_occurrence_evidence "
                    "WHERE occurrence_id = :occurrence_id ORDER BY item_sequence_index",
                    occurrence_id=occ_b,
                )
                if rows:
                    evidence_ids_while_held = [row[0] for row in rows]
                    semantic_while_held = normalized_evidence_for_occurrence(conn_observer, occ_b)
                    break
                time.sleep(0.05)

            assert thread.is_alive(), (
                "Worker B completed before the blocker released its FOR KEY SHARE lock -- "
                "the lock did not actually force activate_occurrence()'s own "
                "SELECT ... FOR UPDATE to wait, so this is not a valid observation barrier."
            )
        finally:
            conn_blocker.run("commit")
            if thread_started:
                thread.join(timeout=_JOIN_TIMEOUT_S)
            conn_blocker.close()

        # From here on, the blocker lock is released and B's real activation
        # attempt has been allowed to run to its real, terminal decision.
        # Every assertion below establishes that the scenario and activation
        # behavior themselves are genuinely correct -- worker completion, no
        # exception, the real DEFERRED outcome, both occurrences' resolution
        # status, and both projections' baseline-unchanged state -- BEFORE
        # this test asserts anything about evidence. That ordering is
        # deliberate: it proves the eventual `evidence_ids_while_held`
        # failure below is attributable solely to durable evidence not yet
        # existing through the production orchestration seam, never to a
        # broken scenario, a mishandled worker, or an unproven DEFERRED.
        assert not thread.is_alive(), "Worker B never completed after the blocker released."
        assert "error" not in worker_result, f"Worker B raised unexpectedly: {worker_result.get('error')!r}"
        assert worker_result.get("outcome") == ActivationOutcome.DEFERRED

        assert activation_status(db_conn, occ_b) is None
        assert activation_outcome(db_conn, occ_b) is None
        # Optional corroboration: A -- the earlier, still-unresolved
        # occurrence B was genuinely deferred behind -- also remains
        # unresolved (it was never activated in this test).
        assert activation_status(db_conn, occ_a) is None
        assert activation_outcome(db_conn, occ_a) is None

        state_after = _current_state_row(db_conn, item_code_raw=ITEM_CODE_RAW)
        assert state_after == baseline_current_state

        history_after = price_history_for(
            db_conn, chain_id=CHAIN_ID, store_id=store_id, item_code_raw=ITEM_CODE_RAW
        )
        assert history_after == baseline_history

        # Only now, with the real DEFERRED outcome and both projections'
        # unchanged baselines already proven, does this test assert
        # anything about durable evidence -- the sole missing behavior.
        assert evidence_ids_while_held, (
            "No normalized_occurrence_evidence rows for B ever became visible to the "
            "observer connection while the blocker held its lock and B's worker was "
            "still genuinely blocked, strictly before B's real DEFERRED decision -- even "
            "though B's real activation attempt genuinely reached and returned DEFERRED, "
            "and every projection (CurrentState, PriceHistory, and A/B resolution status) "
            "is confirmed unchanged above. activate_normalized_occurrence() does not yet "
            "call persist_normalized_occurrence_evidence() at all -- the frozen "
            "resolve -> build items -> persist evidence -> attempt activation sequence is "
            "not wired into production yet."
        )
        assert semantic_while_held is not None
        assert len(semantic_while_held) == len(evidence_ids_while_held)

        evidence_after_rows = conn_observer.run(
            "SELECT evidence_id FROM normalized_occurrence_evidence "
            "WHERE occurrence_id = :occurrence_id ORDER BY item_sequence_index",
            occurrence_id=occ_b,
        )
        evidence_ids_after = [row[0] for row in evidence_after_rows]
        assert evidence_ids_after == evidence_ids_while_held, (
            "The same evidence_id values observed while the blocker held its lock must "
            "remain, unchanged and un-duplicated, after B's real DEFERRED outcome."
        )

        semantic_after = normalized_evidence_for_occurrence(conn_observer, occ_b)
        assert semantic_after == semantic_while_held
    finally:
        conn_worker.close()
        conn_observer.close()
