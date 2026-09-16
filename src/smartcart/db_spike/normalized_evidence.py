"""Durable, immutable normalized occurrence replay evidence (T13 Slice A).

Frozen pipeline semantics (T13, owner-approved design):

    RAW -> parse -> normalize -> identity resolution
        -> DURABLY persist immutable normalized occurrence evidence
        -> projection activation

Evidence persistence here is a seam of its own, independent of
`smartcart.db_spike.activation.activate_occurrence()`: it is not
implemented by calling that function, and it does not run inside, or
depend on, that function's transaction. This is deliberate -- a future
slice (not implemented here) needs evidence to remain durable even when
projection activation is later deferred or never attempted, and that is
only possible if evidence persistence has its own, independent commit
boundary. This module makes no claim about that future behavior; it only
establishes the persistence/read seam and its own fail-closed consistency
guard.

Fail-closed consistency (mirrors, and is necessitated by,
`activate_occurrence()`'s own inline agreement guard -- see that
function's docstring -- which cannot protect evidence committed before it
ever runs): every supplied item's `retailer_chain_id`, `resolved_store_id`,
and `collected_at` must agree with the target occurrence's own durable
`chain_id`, `store_id`, and `collected_at` (read from `artifact_occurrence`)
before anything is inserted. The entire supplied sequence is validated
before the first row is written -- a mismatch anywhere in the sequence
must leave zero durable evidence for that call, never a partial write.

Semantic item order: `item_sequence_index` records each item's position in
the sequence it was supplied in. It is the ONLY signal read-back ordering
relies on -- never `evidence_id` (a plain operational surrogate primary
key), physical row order, or `item_code_raw`.

Replay classification (idempotent/non-duplicating persistence on replay):
`persist_normalized_occurrence_evidence` locks the referenced `store` row
(`FOR KEY SHARE`) then the target `artifact_occurrence` row (`FOR NO KEY
UPDATE`) -- that fixed order, never the reverse, because
`activate_occurrence()` (src/smartcart/db_spike/activation.py) already
locks `store` before it ever touches `artifact_occurrence`; locking in the
opposite order here would create a lock-ordering deadlock against a
concurrent activation. Once both locks are held, existing durable evidence
for the occurrence (if any) is compared, field-by-field and in order,
against the supplied items: no existing evidence inserts the batch;
identical ordered semantic evidence is a genuine no-op (returns None,
writes nothing); anything else -- including a different item order or
count -- is a conflicting replay, rejected with ValueError, leaving the
original evidence completely unchanged. The occurrence lock is what makes
two concurrent identical replays converge on exactly one durable batch:
whichever caller acquires the lock second observes the first caller's
already-committed evidence as identical and writes nothing.

Deliberately NOT implemented in this slice (later RED tests, not this
module): any provenance/contract-version or transformation-behavior
column, any versioned-correction mechanism for a conflicting replay, and
anything to do with rebuild or publication. Adding any of those now would
be scope creep beyond what T13 RED-1/RED-13/RED-2/RED-3 and this
increment's Owner-frozen replay decisions require.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import pg8000.native

from smartcart.db_spike.activation import NormalizedActivationItem
from smartcart.db_spike.db import transaction


@dataclass(frozen=True)
class NormalizedOccurrenceEvidenceRecord:
    """One persisted normalized item's replay evidence, read back from
    normalized_occurrence_evidence.

    Deliberately NOT `NormalizedActivationItem` itself: read-back evidence
    must remain free to later expose additional provenance (a future
    slice's concern) that type has no field for.
    """

    retailer_chain_id: str
    resolved_store_id: int
    item_code_raw: str
    price: Decimal
    price_raw: str
    collected_at: datetime
    product_name: str
    declared_quantity: Decimal
    declared_quantity_raw: str
    declared_quantity_unit_raw: str
    is_weighted: bool | None


def persist_normalized_occurrence_evidence(
    conn: pg8000.native.Connection,
    *,
    occurrence_id: int,
    items: Sequence[NormalizedActivationItem],
) -> None:
    """Durably persist one occurrence's normalized replay evidence, in the
    exact supplied sequence -- atomically and exactly once, whether this
    call is the first for the occurrence, an identical replay (sequential
    or concurrent), or a conflicting replay.

    items=[] is a minimal, distinct case, preserved exactly as before this
    replay behavior existed (docs/work-log.md WL-0036 Note B): occurrence
    existence is still validated (raises ValueError if missing), but an
    empty batch never opens a transaction and never enters replay
    classification below -- it simply returns None once existence is
    confirmed.

    For a non-empty batch, this function opens its own transaction --
    independent of, and never nested inside, activate_occurrence()'s own
    -- and, inside it, acquires two locks in this fixed order: the
    referenced `store` row first (`SELECT ... FOR KEY SHARE`), then the
    target `artifact_occurrence` row second (`SELECT ... FOR NO KEY
    UPDATE`). This exact order is required: `activate_occurrence()` always
    locks `store` before it ever touches `artifact_occurrence`, so locking
    in the opposite order here would create a lock-ordering deadlock
    against a concurrent activation attempt for the same store. The
    occurrence lock also serializes any two concurrent callers of this
    function for the same occurrence, which is what makes the classification
    below converge on exactly one durable batch.

    The plain, unlocked pre-transaction read above (used only to learn
    which `store` row to lock first), and the later locked re-read once
    both locks are held, are both valid because `chain_id`, `store_id`,
    and `collected_at` are immutable occurrence facts under ADR 0011 §8
    (Owner-approved, system-wide) -- they cannot change between the first
    read and the lock acquired moments later, nor at any other time, and
    routine production code cannot delete the row out from under either
    read. Any future correction or revalidation of these facts must be
    additive (a new occurrence or a future correction/version event, not
    yet built), never a mutation of the row this function reads.
    `activation_completed_at`/`activation_outcome` are explicitly separate
    operational metadata, excluded from this immutability guarantee, and
    are never read or relied upon here.

    Once both locks are held, every supplied item's retailer_chain_id/
    resolved_store_id/collected_at is validated against the occurrence's
    own durable chain_id/store_id/collected_at, read fresh under the lock
    (raises ValueError; a mismatch leaves zero durable evidence for this
    call -- the whole transaction rolls back).

    Replay classification (evaluated only after the locks and the
    agreement check above both pass), comparing the complete ordered
    semantic content of any existing durable evidence for this occurrence
    against the supplied items -- every field that defines normalized-
    evidence semantics (chain, resolved store, raw item code, normalized
    and raw price, collected-at, product name, normalized and raw declared
    quantity, raw quantity unit, weighted flag), in item_sequence_index
    order, excluding surrogate/operational metadata (evidence_id,
    created_at) entirely:

    - No existing evidence: insert exactly one ordered batch (the supplied
      items).
    - Existing evidence whose complete ordered semantic content exactly
      matches the supplied items (an identical replay): no write, return
      None.
    - Anything else -- including the same items in a different order, or a
      different item count -- is a conflicting replay: raises ValueError,
      leaving the existing evidence completely unchanged (never appended,
      overwritten, or partially applied).
    """
    existence_rows = conn.run(
        "SELECT chain_id, store_id FROM artifact_occurrence WHERE occurrence_id = :occurrence_id",
        occurrence_id=occurrence_id,
    )
    if not existence_rows:
        raise ValueError(f"Occurrence {occurrence_id} does not exist.")

    if not items:
        return None

    pre_lock_store_id = existence_rows[0][1]

    with transaction(conn):
        # Lock order: store (FOR KEY SHARE) before artifact_occurrence
        # (FOR NO KEY UPDATE) -- see this function's docstring.
        conn.run(
            "SELECT store_id FROM store WHERE store_id = :store_id FOR KEY SHARE",
            store_id=pre_lock_store_id,
        )
        chain_id, store_id, collected_at = conn.run(
            "SELECT chain_id, store_id, collected_at FROM artifact_occurrence "
            "WHERE occurrence_id = :occurrence_id FOR NO KEY UPDATE",
            occurrence_id=occurrence_id,
        )[0]

        for item in items:
            if item.retailer_chain_id != chain_id:
                raise ValueError(
                    f"NormalizedActivationItem.retailer_chain_id "
                    f"{item.retailer_chain_id!r} does not match occurrence "
                    f"{occurrence_id}'s chain_id {chain_id!r}."
                )
            if item.resolved_store_id != store_id:
                raise ValueError(
                    f"NormalizedActivationItem.resolved_store_id "
                    f"{item.resolved_store_id!r} does not match occurrence "
                    f"{occurrence_id}'s store_id {store_id!r}."
                )
            if item.collected_at != collected_at:
                raise ValueError(
                    f"NormalizedActivationItem.collected_at "
                    f"{item.collected_at!r} does not match occurrence "
                    f"{occurrence_id}'s collected_at {collected_at!r}."
                )

        existing_rows = conn.run(
            """
            SELECT chain_id, store_id, item_code_raw, price, price_raw, collected_at,
                   product_name, declared_quantity, declared_quantity_raw,
                   declared_quantity_unit_raw, is_weighted
            FROM normalized_occurrence_evidence
            WHERE occurrence_id = :occurrence_id
            ORDER BY item_sequence_index
            """,
            occurrence_id=occurrence_id,
        )

        if existing_rows:
            existing_semantic = [tuple(row) for row in existing_rows]
            supplied_semantic = [
                (
                    item.retailer_chain_id,
                    item.resolved_store_id,
                    item.item_code_raw,
                    item.price,
                    item.price_raw,
                    item.collected_at,
                    item.product_name,
                    item.declared_quantity,
                    item.declared_quantity_raw,
                    item.declared_quantity_unit_raw,
                    item.is_weighted,
                )
                for item in items
            ]
            if existing_semantic == supplied_semantic:
                return None
            raise ValueError(
                f"Occurrence {occurrence_id} already has durable normalized evidence "
                "whose semantic content disagrees with this replay; conflicting replay "
                "is rejected."
            )

        for index, item in enumerate(items):
            conn.run(
                """
                INSERT INTO normalized_occurrence_evidence (
                    occurrence_id, item_sequence_index, chain_id, store_id,
                    item_code_raw, price, price_raw, collected_at, product_name,
                    declared_quantity, declared_quantity_raw,
                    declared_quantity_unit_raw, is_weighted
                ) VALUES (
                    :occurrence_id, :item_sequence_index, :chain_id, :store_id,
                    :item_code_raw, :price, :price_raw, :collected_at, :product_name,
                    :declared_quantity, :declared_quantity_raw,
                    :declared_quantity_unit_raw, :is_weighted
                )
                """,
                occurrence_id=occurrence_id,
                item_sequence_index=index,
                chain_id=item.retailer_chain_id,
                store_id=item.resolved_store_id,
                item_code_raw=item.item_code_raw,
                price=item.price,
                price_raw=item.price_raw,
                collected_at=item.collected_at,
                product_name=item.product_name,
                declared_quantity=item.declared_quantity,
                declared_quantity_raw=item.declared_quantity_raw,
                declared_quantity_unit_raw=item.declared_quantity_unit_raw,
                is_weighted=item.is_weighted,
            )
    return None


def normalized_evidence_for_occurrence(
    conn: pg8000.native.Connection, occurrence_id: int
) -> list[NormalizedOccurrenceEvidenceRecord]:
    """Read back one occurrence's persisted normalized replay evidence, in
    its original semantic sequence (ordered by item_sequence_index, never
    evidence_id or physical row order). Reads persisted evidence only --
    never invokes parsing, normalization, or store resolution.
    """
    rows = conn.run(
        """
        SELECT chain_id, store_id, item_code_raw, price, price_raw, collected_at,
               product_name, declared_quantity, declared_quantity_raw,
               declared_quantity_unit_raw, is_weighted
        FROM normalized_occurrence_evidence
        WHERE occurrence_id = :occurrence_id
        ORDER BY item_sequence_index
        """,
        occurrence_id=occurrence_id,
    )
    return [
        NormalizedOccurrenceEvidenceRecord(
            retailer_chain_id=row[0],
            resolved_store_id=row[1],
            item_code_raw=row[2],
            price=row[3],
            price_raw=row[4],
            collected_at=row[5],
            product_name=row[6],
            declared_quantity=row[7],
            declared_quantity_raw=row[8],
            declared_quantity_unit_raw=row[9],
            is_weighted=row[10],
        )
        for row in rows
    ]
