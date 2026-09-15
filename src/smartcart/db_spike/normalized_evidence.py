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

Deliberately NOT implemented in this slice (later RED tests, not this
module): idempotent/non-duplicating persistence on replay, any
provenance/contract-version or transformation-behavior column, and
anything to do with rebuild or publication. Adding any of those now would
be scope creep beyond what T13 RED-1/RED-13 require.
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
    exact supplied sequence.

    Fails closed, before any row is written, if any item's
    retailer_chain_id/resolved_store_id/collected_at disagrees with the
    target occurrence's own durable chain_id/store_id/collected_at
    (raises ValueError; the entire sequence is validated first, so a
    mismatch anywhere leaves zero durable evidence for this call).

    Independent of, and never nested inside, activate_occurrence()'s own
    transaction -- this commits on its own.
    """
    identity_rows = conn.run(
        "SELECT chain_id, store_id, collected_at FROM artifact_occurrence "
        "WHERE occurrence_id = :occurrence_id",
        occurrence_id=occurrence_id,
    )
    if not identity_rows:
        raise ValueError(f"Occurrence {occurrence_id} does not exist.")
    chain_id, store_id, collected_at = identity_rows[0]

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

    with transaction(conn):
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
