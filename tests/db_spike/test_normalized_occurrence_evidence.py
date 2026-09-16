"""SmartCart Ingestion TDD -- T13 Slice A. Originally scoped to RED-1 and
RED-13 only; now also covers RED-3 and its two Owner-frozen replay
companions (see the corrected coverage list below).

RED-13 is a stable historical identifier (T13's 13-test frozen matrix),
not execution order -- it is written now, alongside RED-1, before any
production implementation, because normalized evidence now commits BEFORE
projection activation: the later inline consistency guard already living
inside activate_occurrence() cannot protect evidence that is already
durable by the time that guard would run. See that test's own docstring
below for its exact contract.

Frozen pipeline semantics (T13, owner-approved design):

    RAW -> parse -> normalize -> identity resolution
        -> DURABLY persist immutable normalized occurrence evidence
        -> projection activation

This file establishes, and this file ALONE proves, the first missing
architectural seam: that projection-complete normalized evidence for one
occurrence can be durably persisted and read back, including the
already-resolved projection identity that activation will actually
consume -- never the raw retailer store token.

This module does not exist yet:

    from smartcart.db_spike.normalized_evidence import (
        normalized_evidence_for_occurrence,
        persist_normalized_occurrence_evidence,
    )

That import is a TEST-SIDE PROPOSAL only (mirrors the same established
pattern already used by tests/db_spike/test_normalized_occurrence_activation.py
for `smartcart.integration.occurrence_activation`): the smallest reasonable
semantic Python-facing contract to express RED-1's one claim, not a frozen
production API and not permission to implement it. This file is expected to
fail at collection (ModuleNotFoundError) until the seam exists.

Deliberately reuses `smartcart.db_spike.activation.NormalizedActivationItem`
as both the input to persist and the shape read back -- it already carries
exactly the payload projection application actually consumes (including
`resolved_store_id`, the post-resolution identity, and no raw-store-token
field at all), so there is no way for a materially incorrect implementation
to accidentally substitute raw store identity for resolved identity: the
type itself has nowhere to put it.

FROZEN (this revision): normalized replay evidence for one occurrence must
preserve the semantic item SEQUENCE projection logic actually consumed --
recoverable independently of DB physical row order, any generated surrogate
id, insertion-order assumptions, or item_code_raw uniqueness/ordering. This
test proves that narrowly: it persists two items whose item_code_raw values
are supplied in DESCENDING order (ITEM_CODE_RAW_2, the numerically larger
value, first; ITEM_CODE_RAW, the smaller, second) and asserts the read-back
sequence preserves that exact supplied order. An implementation that
recovers sequence via `ORDER BY item_code_raw` (ascending, the natural/
default choice) would return the two items reversed, failing this test --
this is deliberate, not an oversight, and is why the two items are not
supplied in item_code_raw-ascending order. Order is asserted by indexing
`evidence[0]`/`evidence[1]` and checking each one's individual semantic
attributes (item_code_raw, price, etc.) against the correspondingly-ordered
input item -- deliberately NOT by whole-object equality against a
NormalizedActivationItem instance (a future evidence record is expected to
carry additional provenance NormalizedActivationItem has no field for --
see RED-4 -- so this test must not freeze readback to that exact Python
type), and never via an ordinal column, an ORDER BY clause, evidence_id
comparison, or any other physical-representation detail, none of which this
test may assume.

Reuses tests/db_spike/round2_support.py's existing seeding helpers
unmodified, exactly as test_activation_normalized.py and
test_normalized_occurrence_activation.py already do -- no store-resolution
setup is duplicated. `seed_store()` is itself the existing store-resolution
seam (`get_or_create_store_by_alias`, unchanged): it resolves the raw/
source retailer store token ("413", its own default filename_store_token)
into the SmartCart-owned resolved `store_id` this test uses as
`resolved_store_id` -- the two distinguishable identities RED-1's contract
requires.

Coverage now present in this file:
- RED-1: semantic item-sequence preservation (this file's original scope,
  `test_normalized_occurrence_evidence_persists_with_resolved_identity`).
- RED-13: occurrence/item agreement fail-closed rejection (this file's
  original scope,
  `test_normalized_occurrence_evidence_rejects_occurrence_item_mismatch_before_commit`).
- RED-3: idempotent/non-duplicating persistence on identical replay
  (`test_red3_identical_replay_is_idempotent_and_non_duplicating`).
- The Owner-frozen conflicting-replay companion: a replay with different
  semantic evidence is rejected, original evidence preserved
  (`test_conflicting_normalized_evidence_replay_is_rejected_without_mutating_original`).
- The concurrent-identical-replay companion: two real, concurrent callers
  converge on exactly one durable batch
  (`test_concurrent_identical_evidence_replay_persists_exactly_one_batch`).

Explicitly NOT covered by this file:
- RED-2: evidence durability when projection activation is DEFERRED --
  covered in tests/db_spike/test_normalized_occurrence_activation.py
  (`test_red2_normalized_evidence_committed_before_and_surviving_real_deferred`),
  because it exercises the orchestration seam
  (`activate_normalized_occurrence`), not persistence in isolation.
- RED-4: two distinct provenance dimensions (shared contract version vs.
  transformation-behavior provenance).
- RED-5: evidence surviving independently of deleted CurrentState/
  PriceHistory.
- Any Slice B (rebuild) or Slice C (publication) behavior.

Does NOT target `activate_occurrence()` as the evidence-creation API, per
the frozen T13 design: evidence persistence is a seam of its own.
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from decimal import Decimal

import pg8000.native
import pytest

from db_spike.round2_support import (
    CHAIN_ID,
    ITEM_CODE_RAW,
    ITEM_CODE_RAW_2,
    collected_at,
    make_occurrence,
    seed_products,
    seed_store,
)
from smartcart.db_spike.activation import NormalizedActivationItem
from smartcart.db_spike.db import connect
from smartcart.db_spike.normalized_evidence import (
    normalized_evidence_for_occurrence,
    persist_normalized_occurrence_evidence,
)


def test_normalized_occurrence_evidence_persists_with_resolved_identity(
    db_conn: pg8000.native.Connection,
) -> None:
    """RED-1 (T13 Slice A). Requirement: T13 frozen design decisions #1
    and (this revision) semantic item-sequence preservation.

    Establishes that projection-complete normalized evidence for one
    legitimate occurrence -- here, a small multi-item sequence -- can be
    durably persisted and read back through the new evidence seam,
    including the already-resolved projection (store) identity (never the
    raw retailer store token, never requiring a future store-resolution
    rerun) AND the exact semantic order the two items were supplied in.

    EXPECTED_RED: ModuleNotFoundError/ImportError -- the
    smartcart.db_spike.normalized_evidence module does not exist yet.
    """
    when = collected_at(6, 0)
    # seed_store() resolves the raw/source retailer store token ("413",
    # its own default filename_store_token) into the SmartCart-owned
    # resolved store_id via the existing, unchanged get_or_create_store_by_
    # alias() seam. resolved_store_id below is that resolved identity --
    # the raw token itself is never passed anywhere near the new evidence
    # seam in this test.
    resolved_store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=resolved_store_id, collected_at_value=when)

    # Deliberately supplied with item_code_raw DESCENDING (ITEM_CODE_RAW_2,
    # the numerically larger value, first) -- an implementation that
    # recovers sequence via `ORDER BY item_code_raw` ascending (the
    # natural/default choice) would return these two reversed, failing
    # the order assertions below. Every other field also differs between
    # the two items, so order is observable through multiple fields, not
    # item_code_raw alone.
    item_first = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price=Decimal("2.00"),
        price_raw="2.00",
        product_name="Second Item Code, First In Sequence",
        declared_quantity=Decimal("2"),
        declared_quantity_raw="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at=when,
    )
    item_second = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW,
        price=Decimal("1.00"),
        price_raw="1.00",
        product_name="First Item Code, Second In Sequence",
        declared_quantity=Decimal("1"),
        declared_quantity_raw="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at=when,
    )

    persist_normalized_occurrence_evidence(
        db_conn, occurrence_id=occ, items=[item_first, item_second]
    )

    evidence = normalized_evidence_for_occurrence(db_conn, occ)

    assert len(evidence) == 2

    # THE semantic-sequence claim: readback preserves the exact supplied
    # order. Asserted by indexing evidence[0]/evidence[1] and checking each
    # one's individual semantic attributes against the correspondingly-
    # ordered input item below -- deliberately NOT whole-object equality
    # against a NormalizedActivationItem instance (a future evidence
    # record may carry additional provenance that type has no field for --
    # RED-4), and never via an ordinal column, ORDER BY, or evidence_id.
    first, second = evidence[0], evidence[1]

    assert first.retailer_chain_id == CHAIN_ID
    assert first.item_code_raw == ITEM_CODE_RAW_2
    assert first.price == Decimal("2.00")
    assert first.price_raw == "2.00"
    assert first.collected_at == when
    assert first.product_name == "Second Item Code, First In Sequence"
    assert first.declared_quantity == Decimal("2")
    assert first.declared_quantity_raw == "2"
    assert first.declared_quantity_unit_raw == "Kilogram"
    assert first.is_weighted is True
    # THE resolved-identity claim: the persisted evidence carries the
    # RESOLVED internal store identity that projection application
    # actually consumes -- not the raw retailer store token used only to
    # create the store-source-alias. NormalizedActivationItem has no
    # raw-store-token field at all, so a future rebuild reading this
    # evidence back can never mistakenly consume raw identity in its
    # place.
    assert first.resolved_store_id == resolved_store_id

    assert second.retailer_chain_id == CHAIN_ID
    assert second.item_code_raw == ITEM_CODE_RAW
    assert second.price == Decimal("1.00")
    assert second.price_raw == "1.00"
    assert second.collected_at == when
    assert second.product_name == "First Item Code, Second In Sequence"
    assert second.declared_quantity == Decimal("1")
    assert second.declared_quantity_raw == "1"
    assert second.declared_quantity_unit_raw == "Liter"
    assert second.is_weighted is False
    assert second.resolved_store_id == resolved_store_id


@pytest.mark.parametrize(
    "mismatched_field",
    ["retailer_chain_id", "resolved_store_id", "collected_at"],
)
def test_normalized_occurrence_evidence_rejects_occurrence_item_mismatch_before_commit(
    db_conn: pg8000.native.Connection,
    mismatched_field: str,
) -> None:
    """RED-13 (T13 Slice A -- stable historical identifier, not execution
    order). Requirement: fail-closed occurrence/item agreement at the
    durable evidence boundary.

    Because normalized evidence now commits BEFORE projection activation
    (the frozen T13 pipeline), the existing chain/store/collected_at
    agreement guard already living inline inside activate_occurrence()
    (src/smartcart/db_spike/activation.py) cannot protect this evidence --
    that guard only ever runs later, inside activate_occurrence()'s own
    transaction, which a DEFERRED or never-attempted activation may not
    reach at all. The evidence-persistence seam must therefore enforce the
    exact same three-way semantic agreement itself, before anything
    becomes durable:

        item.retailer_chain_id  == artifact_occurrence.chain_id
        item.resolved_store_id  == artifact_occurrence.store_id
        item.collected_at       == artifact_occurrence.collected_at

    Each parametrized case changes exactly ONE of these three dimensions
    away from a legitimate, agreeing baseline item -- every other field,
    including the other two agreement dimensions, remains legitimate.

    EXPECTED_RED (today): ModuleNotFoundError/ImportError -- the
    smartcart.db_spike.normalized_evidence module does not exist yet, same
    as RED-1. Once that module exists, the expected contract per case is:
    persist_normalized_occurrence_evidence() raises ValueError (the exact
    message text is deliberately not frozen -- it mirrors the existing
    activation guard's own choice of exception type for this same class of
    mismatch), and normalized_evidence_for_occurrence() subsequently
    reports zero rows for that occurrence -- i.e. reject, with zero
    durable evidence, never a partial write.

    Deliberately NOT tested here (later RED tests / other slices): DEFERRED
    activation behavior (RED-2), idempotent replay (RED-3), provenance
    versions (RED-4), CurrentState/PriceHistory independence (RED-5), or
    any rebuild/publication behavior. This test is only about occurrence/
    item agreement at the evidence boundary itself.
    """
    when = collected_at(9, 0)
    resolved_store_id = seed_store(db_conn)
    seed_products(db_conn)
    occ = make_occurrence(db_conn, store_id=resolved_store_id, collected_at_value=when)

    # A second, genuinely different resolved store under the same chain --
    # used only by the resolved_store_id mismatch case, so that case is a
    # real disagreement rather than an accidental collision.
    other_resolved_store_id = seed_store(db_conn, filename_store_token="999")

    item_kwargs: dict[str, object] = {
        "retailer_chain_id": CHAIN_ID,
        "resolved_store_id": resolved_store_id,
        "item_code_raw": ITEM_CODE_RAW,
        "price": Decimal("6.90"),
        "price_raw": "6.90",
        "product_name": "Legitimate Name",
        "declared_quantity": Decimal("1"),
        "declared_quantity_raw": "1",
        "declared_quantity_unit_raw": "Liter",
        "is_weighted": False,
        "collected_at": when,
    }

    if mismatched_field == "retailer_chain_id":
        item_kwargs["retailer_chain_id"] = "0000000000000"
    elif mismatched_field == "resolved_store_id":
        item_kwargs["resolved_store_id"] = other_resolved_store_id
    elif mismatched_field == "collected_at":
        item_kwargs["collected_at"] = when + timedelta(minutes=5)

    mismatched_item = NormalizedActivationItem(**item_kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        persist_normalized_occurrence_evidence(db_conn, occurrence_id=occ, items=[mismatched_item])

    # THE zero-durable-evidence claim: rejection must leave nothing behind
    # -- not a partial write, not evidence written before validation ran.
    evidence = normalized_evidence_for_occurrence(db_conn, occ)
    assert len(evidence) == 0


def test_red3_identical_replay_is_idempotent_and_non_duplicating(
    db_conn: pg8000.native.Connection,
) -> None:
    """RED-3 (T13 Slice A). Requirement, per this file's own earlier
    "Explicitly NOT asserted" list (see RED-1's docstring above): "RED-3:
    idempotent/non-duplicating persistence on replay." This test reaches
    that persistence behavior directly and independently -- it does not
    call `activate_normalized_occurrence()` or `activate_occurrence()` at
    all, and does not depend on RED-2 (evidence-before-DEFERRED
    orchestration) being implemented. It calls the real
    `persist_normalized_occurrence_evidence()` -- the same production seam
    RED-1 exercises -- twice, with the exact same occurrence, the exact
    same resolved store, and the exact same semantic item sequence, and
    proves the second call is a genuine no-op: no additional
    `normalized_occurrence_evidence` rows, the same ordered `evidence_id`
    values, and the same semantic readback through the real production
    helper `normalized_evidence_for_occurrence()`.

    EXPECTED RED (today): the second call inserts a second full set of
    rows. `persist_normalized_occurrence_evidence()`
    (src/smartcart/db_spike/normalized_evidence.py) performs a plain
    `INSERT` per item with no `ON CONFLICT` clause, and
    `normalized_occurrence_evidence` (migration 0008) has no uniqueness
    constraint on `(occurrence_id, item_sequence_index)` or
    `(occurrence_id, item_code_raw)` -- by design, per that migration's own
    comment, RED-3 is exactly what was deliberately deferred. So this call
    durably persists 4 rows total instead of 2, the second call's
    `evidence_id` values are new and additional (never equal to the
    first call's), and the semantic readback doubles in length. The RED is
    attributable exactly to that missing idempotency behavior, not to test
    mechanics.

    Scope note (identical replay only): this test covers identical replay
    only -- replaying the same occurrence with the exact same semantic
    item sequence. Conflicting replay -- the same occurrence_id replayed
    with DIFFERENT semantic normalized evidence -- is now frozen
    separately by its own Owner decision (explicit rejection; the original
    evidence must remain unchanged; no row may be appended, overwritten,
    deleted, or replaced; a future versioned-correction mechanism is
    separate, unfrozen work), and is covered by its own companion test,
    `test_conflicting_normalized_evidence_replay_is_rejected_without_mutating_original`,
    below. It is not this test's concern.
    """
    when = collected_at(7, 0)
    resolved_store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=resolved_store_id, collected_at_value=when)

    item_first = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price=Decimal("2.00"),
        price_raw="2.00",
        product_name="Second Item Code, First In Sequence",
        declared_quantity=Decimal("2"),
        declared_quantity_raw="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at=when,
    )
    item_second = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW,
        price=Decimal("1.00"),
        price_raw="1.00",
        product_name="First Item Code, Second In Sequence",
        declared_quantity=Decimal("1"),
        declared_quantity_raw="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at=when,
    )
    items = [item_first, item_second]

    def _evidence_ids() -> list[int]:
        rows = db_conn.run(
            "SELECT evidence_id FROM normalized_occurrence_evidence "
            "WHERE occurrence_id = :occurrence_id ORDER BY item_sequence_index",
            occurrence_id=occ,
        )
        return [row[0] for row in rows]

    persist_normalized_occurrence_evidence(db_conn, occurrence_id=occ, items=items)

    evidence_ids_first = _evidence_ids()
    assert len(evidence_ids_first) == 2
    semantic_first = normalized_evidence_for_occurrence(db_conn, occ)
    assert len(semantic_first) == 2

    # The identical replay: same occurrence, same resolved store (implicit
    # in the unchanged items), same exact semantic item sequence.
    persist_normalized_occurrence_evidence(db_conn, occurrence_id=occ, items=items)

    evidence_ids_second = _evidence_ids()
    assert evidence_ids_second == evidence_ids_first, (
        f"Identical replay must not create additional evidence rows -- expected the same "
        f"ordered evidence_id values {evidence_ids_first}, got {evidence_ids_second}."
    )

    semantic_second = normalized_evidence_for_occurrence(db_conn, occ)
    assert semantic_second == semantic_first


def test_conflicting_normalized_evidence_replay_is_rejected_without_mutating_original(
    db_conn: pg8000.native.Connection,
) -> None:
    """Owner-frozen requirement (T13 Slice A, current bounded increment) --
    a distinct tests-first obligation, not one of the 13 numbered T13 RED
    tests and not itself "RED-3": when the same occurrence_id is replayed
    through `persist_normalized_occurrence_evidence()` with DIFFERENT
    semantic normalized evidence (a genuine conflict, not the identical
    replay `test_red3_identical_replay_is_idempotent_and_non_duplicating`
    above covers), the conflicting replay must be rejected explicitly, the
    original evidence must remain completely unchanged, and no row may be
    appended, overwritten, deleted, or replaced. A future versioned-
    correction mechanism is separate, unfrozen work and is neither
    implemented nor implied here.

    Scenario: persist one valid normalized-evidence batch for one
    occurrence through the real production seam. Capture the ordered
    `evidence_id` values (read-only SQL) and the semantic readback
    (`normalized_evidence_for_occurrence()`). Build a second, structurally
    valid batch for the exact same occurrence, resolved store,
    collected_at, and item_code_raw sequence, differing in exactly one
    semantic field -- the first item's `product_name` -- and call
    `persist_normalized_occurrence_evidence()` again.

    Frozen outcome this test asserts: the conflicting call must raise
    `ValueError` (consistent with this seam's existing fail-closed
    validation convention -- see
    `test_normalized_occurrence_evidence_rejects_occurrence_item_mismatch_before_commit`
    above -- exact message text not frozen), create no additional
    evidence rows, and leave both the original ordered `evidence_id`
    values and the original semantic readback exactly as they were.

    RED construction: the conflicting call is wrapped in a bare
    `except Exception` used ONLY to observe and retain whatever was
    raised (or wasn't) -- never to suppress or short-circuit. After the
    call, evidence IDs and semantic evidence are always re-queried,
    regardless of what happened. Violations are collected independently
    for: no exception was raised; the exception raised was not
    `ValueError` (an unexpected exception type is reported as a violation,
    never accepted as a successful rejection); evidence_id values changed;
    semantic evidence changed. Exactly one final assertion fires over the
    complete violation collection.

    EXPECTED RED (today): `persist_normalized_occurrence_evidence()`
    (src/smartcart/db_spike/normalized_evidence.py) has no check at all
    against pre-existing evidence for the same occurrence_id -- it only
    validates the supplied items' chain_id/resolved_store_id/collected_at
    against the occurrence's own identity, then unconditionally INSERTs.
    So the conflicting call raises no exception, silently appends a second
    full set of rows (carrying the changed product_name), and both the
    evidence_id sequence and the semantic readback change. Every violation
    dimension checked is expected to fire except "wrong exception type"
    (no exception is raised at all today, so that branch does not apply).
    """
    when = collected_at(8, 0)
    resolved_store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=resolved_store_id, collected_at_value=when)

    item_first = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price=Decimal("2.00"),
        price_raw="2.00",
        product_name="Second Item Code, First In Sequence",
        declared_quantity=Decimal("2"),
        declared_quantity_raw="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at=when,
    )
    item_second = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW,
        price=Decimal("1.00"),
        price_raw="1.00",
        product_name="First Item Code, Second In Sequence",
        declared_quantity=Decimal("1"),
        declared_quantity_raw="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at=when,
    )
    original_items = [item_first, item_second]

    def _evidence_ids() -> list[int]:
        rows = db_conn.run(
            "SELECT evidence_id FROM normalized_occurrence_evidence "
            "WHERE occurrence_id = :occurrence_id ORDER BY item_sequence_index",
            occurrence_id=occ,
        )
        return [row[0] for row in rows]

    persist_normalized_occurrence_evidence(db_conn, occurrence_id=occ, items=original_items)

    evidence_ids_original = _evidence_ids()
    assert len(evidence_ids_original) == 2
    semantic_original = normalized_evidence_for_occurrence(db_conn, occ)
    assert len(semantic_original) == 2

    # Conflicting replay: same occurrence, same resolved store, same
    # collected_at, same item_code_raw sequence -- exactly one semantic
    # field (the first item's product_name) genuinely differs from the
    # original.
    conflicting_item_first = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price=Decimal("2.00"),
        price_raw="2.00",
        product_name="Second Item Code, First In Sequence -- CONFLICTING REPLAY",
        declared_quantity=Decimal("2"),
        declared_quantity_raw="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at=when,
    )
    conflicting_items = [conflicting_item_first, item_second]

    caught: BaseException | None = None
    try:
        persist_normalized_occurrence_evidence(db_conn, occurrence_id=occ, items=conflicting_items)
    except Exception as exc:  # noqa: BLE001 -- caught only for observation, never suppressed
        caught = exc

    evidence_ids_after = _evidence_ids()
    semantic_after = normalized_evidence_for_occurrence(db_conn, occ)

    violations: list[str] = []
    if caught is None:
        violations.append("no exception was raised for the conflicting replay")
    elif not isinstance(caught, ValueError):
        violations.append(
            f"the exception raised was {type(caught).__name__}, not ValueError: {caught!r}"
        )
    if evidence_ids_after != evidence_ids_original:
        violations.append(
            f"evidence_id values changed -- expected {evidence_ids_original}, got "
            f"{evidence_ids_after}"
        )
    if semantic_after != semantic_original:
        violations.append("semantic evidence changed from the original persisted batch")

    assert not violations, (
        "Conflicting normalized-evidence replay must be rejected without mutating the "
        f"original evidence; violations observed: {violations}"
    )


_BLOCKER_LOCK_TIMEOUT_S = 3.0
_JOIN_TIMEOUT_S = 10.0
_MAX_BLOCKING_TRAVERSAL_EDGES = 3


def _blocking_graph_reaches(
    observer: pg8000.native.Connection,
    start_pid: int,
    target_pid: int,
    *,
    max_edges: int,
) -> tuple[bool, dict[int, list[int]]]:
    """Breadth-first traversal of the real PostgreSQL lock-wait graph,
    starting from `start_pid`, following `pg_blocking_pids()` edges, looking
    for `target_pid` within `max_edges` hops. A `visited` set prevents
    cycles. Returns `(reached, edges)`: `edges` maps every PID actually
    queried to the blocking PIDs `pg_blocking_pids()` reported for it --
    returned regardless of whether `target_pid` was reached, so a caller
    can report the full observed graph on failure.

    Needed because PostgreSQL's `pg_blocking_pids(pid)` may report a
    waiting process that is merely ahead of `pid` in the row-lock wait
    queue -- a soft/intermediate blocker -- rather than the ultimate
    holder of the conflicting lock: when two transactions both request a
    self-conflicting lock mode (`FOR NO KEY UPDATE` here) on a row a third
    transaction already holds a conflicting lock on, PostgreSQL's tuple-
    level lock queue can chain the second waiter behind the *first waiter*
    (`wait_event=tuple`) instead of directly behind the original holder
    (`wait_event=transactionid`) -- observed via direct `pg_stat_activity`
    inspection outside this test suite. So `pg_blocking_pids()` does not
    guarantee that the intended root blocker is directly listed for every
    worker; one worker's immediately-reported blocker can be the *other
    worker's* PID instead, even though the blocker is still the true root
    cause. A one-hop check against the blocker PID directly is therefore
    not a valid observation for this lock mode; bounded transitive
    reachability is required.
    """
    edges: dict[int, list[int]] = {}
    visited = {start_pid}
    frontier = [start_pid]
    for _ in range(max_edges):
        next_frontier: list[int] = []
        for pid in frontier:
            rows = observer.run("SELECT pg_blocking_pids(:pid)", pid=pid)
            blockers = list(rows[0][0] or [])
            edges[pid] = blockers
            if target_pid in blockers:
                return True, edges
            for candidate in blockers:
                if candidate not in visited:
                    visited.add(candidate)
                    next_frontier.append(candidate)
        if not next_frontier:
            break
        frontier = next_frontier
    return False, edges


def test_concurrent_identical_evidence_replay_persists_exactly_one_batch(
    db_conn: pg8000.native.Connection, db_dsn: str
) -> None:
    """Distinct tests-first obligation for the current T13 bounded increment
    -- not one of the 13 numbered T13 RED tests and not itself "RED-3": two
    real, concurrent calls to `persist_normalized_occurrence_evidence()`,
    from two separate real connections, for the SAME occurrence, the SAME
    resolved store, and the SAME non-empty ordered semantic item sequence,
    must durably persist exactly ONE evidence batch, not two. This is the
    concurrent counterpart of
    `test_red3_identical_replay_is_idempotent_and_non_duplicating` (which
    proves SEQUENTIAL identical replay is idempotent) and of
    `test_conflicting_normalized_evidence_replay_is_rejected_without_mutating_original`
    (which proves SEQUENTIAL conflicting replay is rejected). Per this
    increment's agreed scope exclusion, a concurrent CONFLICTING replay is
    deliberately NOT covered here: once all persistence calls are
    serialized by whatever mechanism eventually resolves this test, a
    concurrent conflict reduces to that same already-covered sequential
    classification path and needs no separate concurrent test of its own.

    Deterministic concurrency arrangement (real PostgreSQL, no production
    test hook, no arbitrary sleep as the sole proof): a BLOCKER connection
    opens its own transaction and takes
    `SELECT occurrence_id FROM artifact_occurrence WHERE occurrence_id = :occurrence_id FOR UPDATE`
    on the target occurrence's own row. Two WORKER connections each run the
    real `persist_normalized_occurrence_evidence()` for the identical
    batch, released together through a `threading.Barrier(2)` so both
    genuinely attempt the call at the same moment rather than accidentally
    running sequentially. Before releasing the blocker, an OBSERVER
    connection performs a bounded-timeout, breadth-first traversal
    (`_blocking_graph_reaches`, at most `_MAX_BLOCKING_TRAVERSAL_EDGES`
    hops, with a visited set preventing cycles) of the real
    `pg_blocking_pids()` wait graph starting from EACH worker's backend PID
    (each captured via `SELECT pg_backend_pid()` on its own worker
    connection before that worker starts), requiring the blocker's own
    backend PID to be transitively reachable from both -- a real
    PostgreSQL lock-manager observation, not a sleep-and-hope. Direct
    reachability (worker -> blocker) and one-hop indirect reachability
    (worker -> the other worker -> blocker) are both accepted; only actual
    reachability of the blocker PID counts, never a bare PID-set
    membership check. `thread.is_alive()` on both workers is checked at
    the same point as corroborating evidence neither completed early.

    Why transitive traversal, not a direct one-hop check, is required:
    `pg_blocking_pids(pid)` can report a process that is merely ahead of
    `pid` in PostgreSQL's row-lock wait queue -- a soft/intermediate
    blocker -- rather than the ultimate holder of the conflicting lock; it
    does not guarantee that the intended root blocker is directly listed
    for every worker. `FOR NO KEY UPDATE` (the occurrence-serialization
    lock `persist_normalized_occurrence_evidence()` now takes) is a
    self-conflicting lock mode, so when both workers request it
    concurrently while the blocker already holds a conflicting lock,
    PostgreSQL's tuple-level lock queue can chain the second worker behind
    the *first worker* instead of directly behind the blocker -- observed
    via direct `pg_stat_activity`/`wait_event` inspection outside this test
    suite, not a flaky race. A literal "blocker PID appears directly in
    both workers' `pg_blocking_pids()`" check is therefore not a valid
    observation for this lock mode, regardless of timeout length; only
    bounded transitive reachability correctly proves both workers are
    genuinely blocked by the same real lock the blocker holds.

    This arrangement is deliberately valid in both the current state and
    the intended future one: today, each worker blocks inside its own
    `INSERT INTO normalized_occurrence_evidence` on the implicit `FOR KEY
    SHARE` foreign-key-protection check that INSERT triggers against
    `artifact_occurrence` (migration 0008's `occurrence_id` FK) -- which
    conflicts with the blocker's `FOR UPDATE`. With the explicit
    occurrence-serialization lock now implemented inside
    `persist_normalized_occurrence_evidence()` itself
    (src/smartcart/db_spike/normalized_evidence.py), each worker instead
    blocks there, on the same `artifact_occurrence` row, for the same
    reason -- the blocker and the transitive observation technique cover
    both cases without needing to change.

    Required outcome after the blocker releases, checked strictly in this
    order so that "both workers genuinely reached the blocker, both
    completed, both returned successfully, neither raised an unrelated
    error" is proven BEFORE this test asserts anything about how many
    evidence batches exist: (1) neither worker thread remains alive after a
    bounded join; (2) neither worker raised an exception; (3) both calls
    returned `None`, the current, unchanged return contract; (4) only then,
    query the durable evidence rows and assert exactly one batch (as many
    rows as the one supplied item sequence, not two); (5) assert the
    ordered semantic readback equals the one supplied batch. This test does
    not distinguish which worker performed the "initial" insert and which
    would, under a correct implementation, have observed an identical
    replay -- that distinction is not meaningful under two calls released
    simultaneously.

    EXPECTED RED (today): `persist_normalized_occurrence_evidence()`
    (src/smartcart/db_spike/normalized_evidence.py) has no replay
    classification and no occurrence-level serialization. Once the blocker
    releases, both workers' blocked INSERTs proceed independently (neither
    worker itself takes any lock that would exclude the other), each
    worker's own transaction fully commits its own two-row batch, and both
    return `None` successfully with no exception. So this test's earlier
    assertions (both threads finished, neither raised, both returned
    `None`) all PASS -- proving the concurrent scenario and its observation
    are genuinely valid -- and the test only then fails because four
    evidence rows (two duplicate batches) exist where exactly two (one
    batch) are required. The RED is attributable exactly to the missing
    concurrent replay classification/serialization, never to thread setup,
    unsupported lock observation, a timeout, or cleanup.
    """
    when = collected_at(9, 0)
    resolved_store_id = seed_store(db_conn)
    seed_products(db_conn, item_codes=(ITEM_CODE_RAW, ITEM_CODE_RAW_2))
    occ = make_occurrence(db_conn, store_id=resolved_store_id, collected_at_value=when)

    item_first = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW_2,
        price=Decimal("2.00"),
        price_raw="2.00",
        product_name="Second Item Code, First In Sequence",
        declared_quantity=Decimal("2"),
        declared_quantity_raw="2",
        declared_quantity_unit_raw="Kilogram",
        is_weighted=True,
        collected_at=when,
    )
    item_second = NormalizedActivationItem(
        retailer_chain_id=CHAIN_ID,
        resolved_store_id=resolved_store_id,
        item_code_raw=ITEM_CODE_RAW,
        price=Decimal("1.00"),
        price_raw="1.00",
        product_name="First Item Code, Second In Sequence",
        declared_quantity=Decimal("1"),
        declared_quantity_raw="1",
        declared_quantity_unit_raw="Liter",
        is_weighted=False,
        collected_at=when,
    )
    items = [item_first, item_second]

    def _evidence_ids() -> list[int]:
        rows = db_conn.run(
            "SELECT evidence_id FROM normalized_occurrence_evidence "
            "WHERE occurrence_id = :occurrence_id ORDER BY item_sequence_index",
            occurrence_id=occ,
        )
        return [row[0] for row in rows]

    conn_worker_1 = connect(db_dsn)
    conn_worker_2 = connect(db_dsn)
    conn_blocker = connect(db_dsn)
    conn_observer = connect(db_dsn)

    worker_1_pid: int = conn_worker_1.run("SELECT pg_backend_pid()")[0][0]
    worker_2_pid: int = conn_worker_2.run("SELECT pg_backend_pid()")[0][0]
    blocker_pid: int = conn_blocker.run("SELECT pg_backend_pid()")[0][0]

    barrier = threading.Barrier(2)
    worker_results: dict[int, tuple[str, object]] = {}

    def make_worker(conn: pg8000.native.Connection, key: int):
        def run() -> None:
            barrier.wait(timeout=_JOIN_TIMEOUT_S)
            try:
                outcome = persist_normalized_occurrence_evidence(
                    conn, occurrence_id=occ, items=items
                )
                worker_results[key] = ("ok", outcome)
            except BaseException as exc:  # noqa: BLE001 -- observed, never suppressed
                worker_results[key] = ("error", exc)

        return run

    thread_1 = threading.Thread(target=make_worker(conn_worker_1, 1))
    thread_2 = threading.Thread(target=make_worker(conn_worker_2, 2))
    threads_started = False

    try:
        try:
            conn_blocker.run("begin")
            conn_blocker.run(
                "SELECT occurrence_id FROM artifact_occurrence "
                "WHERE occurrence_id = :occurrence_id FOR UPDATE",
                occurrence_id=occ,
            )

            thread_1.start()
            thread_2.start()
            threads_started = True

            deadline = time.monotonic() + _BLOCKER_LOCK_TIMEOUT_S
            both_blocked = False
            last_edges_1: dict[int, list[int]] = {}
            last_edges_2: dict[int, list[int]] = {}
            while time.monotonic() < deadline:
                reached_1, last_edges_1 = _blocking_graph_reaches(
                    conn_observer,
                    worker_1_pid,
                    blocker_pid,
                    max_edges=_MAX_BLOCKING_TRAVERSAL_EDGES,
                )
                reached_2, last_edges_2 = _blocking_graph_reaches(
                    conn_observer,
                    worker_2_pid,
                    blocker_pid,
                    max_edges=_MAX_BLOCKING_TRAVERSAL_EDGES,
                )
                if reached_1 and reached_2:
                    both_blocked = True
                    break
                time.sleep(0.05)

            assert thread_1.is_alive() and thread_2.is_alive(), (
                "At least one worker completed before the blocker released its FOR UPDATE "
                "lock on artifact_occurrence -- both workers must genuinely reach and wait "
                "at the blocker for this to be a valid concurrent observation."
            )
            assert both_blocked, (
                f"blocker backend {blocker_pid} was not transitively reachable (within "
                f"{_MAX_BLOCKING_TRAVERSAL_EDGES} pg_blocking_pids() edges, cycles excluded) "
                f"from both worker backends ({worker_1_pid}, {worker_2_pid}) within "
                f"{_BLOCKER_LOCK_TIMEOUT_S}s -- this is not a valid concurrency observation. "
                f"Last observed blocking edges from worker 1 ({worker_1_pid}): {last_edges_1!r}; "
                f"from worker 2 ({worker_2_pid}): {last_edges_2!r}."
            )
        finally:
            conn_blocker.run("commit")
            if threads_started:
                thread_1.join(timeout=_JOIN_TIMEOUT_S)
                thread_2.join(timeout=_JOIN_TIMEOUT_S)
            conn_blocker.close()

        # From here on, both workers are proven to have genuinely reached
        # and waited at the same real blocker before it released. Every
        # assertion below establishes that the concurrent attempt itself
        # was valid -- both threads finished, neither raised, both returned
        # successfully under the current None contract -- BEFORE this test
        # asserts anything about how many evidence batches exist.
        assert not thread_1.is_alive()
        assert not thread_2.is_alive()
        assert worker_results.get(1, ("missing",))[0] == "ok", (
            f"Worker 1 did not complete successfully: {worker_results.get(1)!r}"
        )
        assert worker_results.get(2, ("missing",))[0] == "ok", (
            f"Worker 2 did not complete successfully: {worker_results.get(2)!r}"
        )
        assert worker_results[1][1] is None
        assert worker_results[2][1] is None

        # Only now, with both workers proven blocked-then-completed
        # successfully, does this test assert anything about durable
        # evidence -- the sole missing behavior.
        evidence_ids_after = _evidence_ids()
        semantic_after = normalized_evidence_for_occurrence(db_conn, occ)

        assert len(evidence_ids_after) == len(items), (
            "Exactly one durable evidence batch (matching the single supplied item sequence) "
            "must exist after two concurrent identical persist_normalized_occurrence_evidence() "
            f"calls for the same occurrence -- expected {len(items)} evidence rows, found "
            f"{len(evidence_ids_after)} ({evidence_ids_after}). There is no concurrent replay "
            "classification or serialization yet, so both workers -- once released from the "
            "same real lock together -- each independently inserted their own full copy of "
            "the batch."
        )

        assert len(semantic_after) == len(items)
        # Complete ordered semantic comparison, field-by-field against the
        # actual NormalizedOccurrenceEvidenceRecord fields (src/smartcart/
        # db_spike/normalized_evidence.py) -- every field that defines
        # normalized-evidence semantics, in supplied order. Not a whole-
        # object `==` (NormalizedOccurrenceEvidenceRecord and
        # NormalizedActivationItem are different dataclass types, so that
        # would never be True regardless of field values). No evidence_id
        # or created_at to exclude and no item_sequence_index/occurrence_id
        # to include -- the readback type exposes neither.
        readback_first, readback_second = semantic_after[0], semantic_after[1]

        assert readback_first.retailer_chain_id == item_first.retailer_chain_id
        assert readback_first.resolved_store_id == item_first.resolved_store_id
        assert readback_first.item_code_raw == item_first.item_code_raw
        assert readback_first.price == item_first.price
        assert readback_first.price_raw == item_first.price_raw
        assert readback_first.collected_at == item_first.collected_at
        assert readback_first.product_name == item_first.product_name
        assert readback_first.declared_quantity == item_first.declared_quantity
        assert readback_first.declared_quantity_raw == item_first.declared_quantity_raw
        assert readback_first.declared_quantity_unit_raw == item_first.declared_quantity_unit_raw
        assert readback_first.is_weighted == item_first.is_weighted

        assert readback_second.retailer_chain_id == item_second.retailer_chain_id
        assert readback_second.resolved_store_id == item_second.resolved_store_id
        assert readback_second.item_code_raw == item_second.item_code_raw
        assert readback_second.price == item_second.price
        assert readback_second.price_raw == item_second.price_raw
        assert readback_second.collected_at == item_second.collected_at
        assert readback_second.product_name == item_second.product_name
        assert readback_second.declared_quantity == item_second.declared_quantity
        assert readback_second.declared_quantity_raw == item_second.declared_quantity_raw
        assert readback_second.declared_quantity_unit_raw == item_second.declared_quantity_unit_raw
        assert readback_second.is_weighted == item_second.is_weighted
    finally:
        conn_worker_1.close()
        conn_worker_2.close()
        conn_observer.close()
