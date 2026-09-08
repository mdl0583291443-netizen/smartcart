"""Minimal shapes for StoreProductCurrentState / PriceHistory, plus Round
2's ordered/atomic/idempotent activation of a valid, store-scoped
ArtifactOccurrence.

Round 1 (`record_price_observation`, `current_state`, `price_history_for`)
only proved these tables can hold data and reference their originating
occurrence atomically as a pair, for ONE observation in isolation. It
deliberately did not implement ordered activation across occurrences for
the same (chain_id, store_id) (Fixed Data Invariant 5.B), the
stale-occurrence policy (Fixed Data Invariant 6), an idempotency/effect
marker, or any cross-occurrence concurrency control.

`activate_occurrence` below is Round 2: it activates every product in one
already-durable, valid, store-scoped ArtifactOccurrence as a single
PostgreSQL transaction, using the occurrence's Store row as the
per-store serialization anchor (`SELECT ... FOR UPDATE`, acquired before
any ordering check, held until commit/rollback). See its docstring for
the full algorithm. `record_price_observation` remains as Round 1 left
it -- unordered, non-idempotent, single-observation -- and must not be
used where ordered/idempotent activation is required.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

import pg8000.native

from smartcart.db_spike.db import transaction


@dataclass(frozen=True)
class PriceObservation:
    chain_id: str
    # SmartCart-owned Store surrogate identity (see catalog.py), never a
    # retailer raw store identifier.
    store_id: int
    item_code_raw: str
    price: Decimal
    price_raw: str
    observed_at: datetime
    source_occurrence_id: int


def record_price_observation(conn: pg8000.native.Connection, observation: PriceObservation) -> int:
    """Atomically upsert StoreProductCurrentState and append one
    PriceHistory event for a single price observation. Returns the new
    price_history_id.

    current_price (typed Decimal) and current_price_raw (the untouched
    source string) both persist -- neither destructively replaces the
    other (Fixed Data Invariant 8).
    """
    with transaction(conn):
        conn.run(
            """
            INSERT INTO store_product_current_state (
                chain_id, store_id, item_code_raw, current_price, current_price_raw,
                source_occurrence_id, updated_at
            ) VALUES (
                :chain_id, :store_id, :item_code_raw, :price, :price_raw,
                :source_occurrence_id, :observed_at
            )
            ON CONFLICT (chain_id, store_id, item_code_raw) DO UPDATE SET
                current_price = excluded.current_price,
                current_price_raw = excluded.current_price_raw,
                source_occurrence_id = excluded.source_occurrence_id,
                updated_at = excluded.updated_at
            """,
            chain_id=observation.chain_id,
            store_id=observation.store_id,
            item_code_raw=observation.item_code_raw,
            price=observation.price,
            price_raw=observation.price_raw,
            source_occurrence_id=observation.source_occurrence_id,
            observed_at=observation.observed_at,
        )
        rows = conn.run(
            """
            INSERT INTO price_history (
                chain_id, store_id, item_code_raw, price, price_raw,
                observed_at, source_occurrence_id
            ) VALUES (
                :chain_id, :store_id, :item_code_raw, :price, :price_raw,
                :observed_at, :source_occurrence_id
            ) RETURNING price_history_id
            """,
            chain_id=observation.chain_id,
            store_id=observation.store_id,
            item_code_raw=observation.item_code_raw,
            price=observation.price,
            price_raw=observation.price_raw,
            observed_at=observation.observed_at,
            source_occurrence_id=observation.source_occurrence_id,
        )
    price_history_id: int = rows[0][0]
    return price_history_id


def current_state(
    conn: pg8000.native.Connection, *, chain_id: str, store_id: int, item_code_raw: str
) -> dict[str, object] | None:
    """Test/inspection helper: one product's current state row, if any."""
    rows = conn.run(
        """
        SELECT current_price, current_price_raw, source_occurrence_id, updated_at
        FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=chain_id,
        store_id=store_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    columns = [c["name"] for c in conn.columns]
    return dict(zip(columns, rows[0], strict=True))


def price_history_for(
    conn: pg8000.native.Connection, *, chain_id: str, store_id: int, item_code_raw: str
) -> list[dict[str, object]]:
    """Test/inspection helper: all PriceHistory rows for one product, in
    insertion order -- append-only, never mutated (Fixed Data Invariant 8)."""
    rows = conn.run(
        """
        SELECT price_history_id, price, price_raw, observed_at, source_occurrence_id
        FROM price_history
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        ORDER BY price_history_id
        """,
        chain_id=chain_id,
        store_id=store_id,
        item_code_raw=item_code_raw,
    )
    columns = [c["name"] for c in conn.columns]
    return [dict(zip(columns, row, strict=True)) for row in rows]


@dataclass(frozen=True)
class ProductPrice:
    """One product's observed price within an occurrence being activated.

    price is the typed Decimal comparison value; price_raw is the
    untouched source string, preserved alongside it (Fixed Data
    Invariant 8). The caller must have already upserted a matching
    chain_product (chain_id, item_code_raw) row -- activate_occurrence
    does not do so itself, consistent with catalog.py owning identity
    upserts.
    """

    item_code_raw: str
    price: Decimal
    price_raw: str


@dataclass(frozen=True)
class NormalizedActivationItem:
    """One item's normalized-contract facts for the normalized activation
    input mode (Schema Slice 2, docs/adr/0011). resolved_store_id is the
    SmartCart surrogate store identity, already resolved outside this
    module (see catalog.py) -- never a raw retailer store identifier.
    normalization_contract_version is not a field here: it is assigned
    internally by normalized persistence, not supplied by the caller."""

    retailer_chain_id: str
    resolved_store_id: int
    item_code_raw: str
    price: Decimal
    price_raw: str
    product_name: str
    declared_quantity: Decimal
    declared_quantity_raw: str
    declared_quantity_unit_raw: str
    is_weighted: bool | None
    collected_at: datetime


class ActivationOutcome(Enum):
    """Terminal result of one activate_occurrence call."""

    #: This occurrence's products were just written to CurrentState/
    #: PriceHistory (typed-price changes only) and it is now resolved.
    APPLIED = "applied"
    #: This occurrence was already resolved by a previous call (this call
    #: made no writes) -- the safe no-op retry-after-commit case.
    ALREADY_APPLIED = "already_applied"
    #: An earlier-ordered occurrence for this store is still unresolved;
    #: no writes were made and this occurrence remains unresolved. The
    #: caller must retry later -- this module does not retry on its own.
    DEFERRED = "deferred"
    #: A later-ordered occurrence for this store already completed
    #: activation; this occurrence is now resolved but its data was never
    #: applied to CurrentState/PriceHistory (the stale-occurrence policy).
    STALE_PRESERVED = "stale_preserved"


class _DeferredError(Exception):
    """Internal control-flow signal: rolls back the open transaction
    without applying any write, then activate_occurrence turns it into
    ActivationOutcome.DEFERRED. Never raised across this module's
    boundary."""


# Checkpoint names activate_occurrence's optional on_checkpoint test hook
# is called with, each paired with a product index (-1 when not tied to a
# specific product). Exercised only by tests that inject failures or pause
# execution to prove rollback/atomicity/independence under real Postgres
# concurrency -- production callers must never pass on_checkpoint.
_CHECKPOINT_BEFORE_CURRENT_STATE = "before_current_state"
_CHECKPOINT_AFTER_CURRENT_STATE = "after_current_state"
_CHECKPOINT_AFTER_PRICE_HISTORY = "after_price_history"
_CHECKPOINT_BEFORE_COMPLETION = "before_completion"


def _current_price(
    conn: pg8000.native.Connection, *, chain_id: str, store_id: int, item_code_raw: str
) -> Decimal | None:
    rows = conn.run(
        """
        SELECT current_price FROM store_product_current_state
        WHERE chain_id = :chain_id AND store_id = :store_id AND item_code_raw = :item_code_raw
        """,
        chain_id=chain_id,
        store_id=store_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    price: Decimal = rows[0][0]
    return price


@dataclass(frozen=True)
class _EffectiveItem:
    """Private, internal-only per-item view the single product loop below
    iterates over -- never exposed outside this module. `normalized` is
    None for a legacy ProductPrice-sourced item; set to the originating
    NormalizedActivationItem for a normalized-mode item, carrying the
    normalized facts the CurrentState write branch below needs."""

    item_code_raw: str
    price: Decimal
    price_raw: str
    normalized: NormalizedActivationItem | None


def activate_occurrence(
    conn: pg8000.native.Connection,
    *,
    occurrence_id: int,
    products: Sequence[ProductPrice],
    normalized_items: Sequence[NormalizedActivationItem] = (),
    on_checkpoint: Callable[[str, int], None] | None = None,
) -> ActivationOutcome:
    """Activate every product in one already-durable, valid, store-scoped
    ArtifactOccurrence as a single PostgreSQL transaction.

    Algorithm (all inside one transaction):

    1. Read the occurrence's immutable identity fields (chain_id,
       store_id, artifact_kind, validation_status, collected_at) -- these
       are set once at insert and never mutated, so reading them requires
       no lock. Raises ValueError if the occurrence does not exist, or is
       not a valid, store-scoped occurrence (this function's contract is
       scoped to exactly that; a non-'pricefull' or non-'valid' occurrence
       never has derived state and must not be passed here).
    2. Lock the occurrence's Store row (`SELECT ... FOR UPDATE`) -- the
       fixed per-store serialization anchor. This is acquired before any
       ordering/idempotency check below, and held until this transaction
       commits or rolls back.
    3. Re-read this occurrence's activation_completed_at, now that the
       Store lock guarantees it reflects every activation already
       committed for this store. If already set, return ALREADY_APPLIED
       with no further writes (idempotent retry-after-commit).
    4. If any other valid, store-scoped occurrence for this store, ordered
       strictly before this one by (collected_at, occurrence_id), is
       still unresolved (activation_completed_at IS NULL), return
       DEFERRED with no writes -- this occurrence stays unresolved for a
       later retry.
    5. If any other valid, store-scoped occurrence for this store, ordered
       strictly after this one, is already resolved, this occurrence is
       stale: mark it resolved (activation_completed_at = now(),
       activation_outcome = 'stale_preserved') without touching
       CurrentState/PriceHistory, and return STALE_PRESERVED.
    6. Otherwise, for each product (typed Decimal price comparison against
       the existing CurrentState row, if any): upsert CurrentState
       unconditionally to the latest observation, and append one
       PriceHistory event only if the typed price genuinely changed (or
       there was no prior CurrentState row) -- formatting-only
       differences (e.g. "7.0" vs "7.00") never create a PriceHistory
       event. The PriceHistory insert is additionally guarded by the
       database's UNIQUE(source_occurrence_id, chain_id, item_code_raw)
       constraint (ON CONFLICT DO NOTHING) as the durable idempotency
       backstop. Then mark this occurrence resolved
       (activation_outcome = 'applied') and return APPLIED.

    activation_completed_at and activation_outcome are always written
    together and are never null independently of each other (enforced by
    a database CHECK constraint, migration 0003): an unresolved occurrence
    has both null; a resolved one has both set, recording not just that
    resolution happened but which of the two terminal shapes it took --
    that distinction is a permanent historical fact, not just an ordering
    signal, and it is stored explicitly rather than made inferrable only
    from whether CurrentState/PriceHistory happen to reference this
    occurrence.

    If any step raises before the transaction commits, the entire
    activation rolls back: no partial CurrentState, no partial
    PriceHistory, no partial resolution -- one multi-product occurrence
    activates as one coherent all-or-nothing store observation.

    on_checkpoint is a test-only hook (never used in production) called
    at fixed points during step 6, as (checkpoint_name, product_index):
    "before_current_state", "after_current_state", "after_price_history"
    (each once per product), and "before_completion" (once, index -1,
    after all products, before marking the occurrence resolved). Tests
    use it to inject a failure (raise) to prove rollback, or to pause
    (block) to prove one store's held lock does not block another
    store's activation.

    normalized_items is Schema Slice 2 (docs/adr/0011): when given, every
    item is validated against this occurrence's own chain_id/store_id/
    collected_at (exact equality, no tolerance/coercion) before any
    CurrentState/price_history mutation begins for this occurrence -- a
    mismatch raises ValueError and leaves the occurrence unresolved,
    exactly like the existing "occurrence does not exist"/wrong-kind/
    wrong-validation-status checks above, never as DEFERRED or
    STALE_PRESERVED or ALREADY_APPLIED. Once validated, each normalized
    item's product_name, declared_quantity, declared_quantity_raw,
    declared_quantity_unit_raw, and is_weighted are written to
    CurrentState alongside current_price/current_price_raw, with
    normalization_contract_version set internally to 1 (never caller-
    supplied); price_history is written identically to the legacy path
    (price-only) in both modes. Exactly one of products/normalized_items
    is expected to be non-empty; that input-mode contract is not yet
    enforced here.
    """
    effective_items: list[_EffectiveItem] = (
        [
            _EffectiveItem(
                item_code_raw=p.item_code_raw, price=p.price, price_raw=p.price_raw, normalized=None
            )
            for p in products
        ]
        if not normalized_items
        else [
            _EffectiveItem(
                item_code_raw=n.item_code_raw, price=n.price, price_raw=n.price_raw, normalized=n
            )
            for n in normalized_items
        ]
    )
    try:
        with transaction(conn):
            identity_rows = conn.run(
                """
                SELECT chain_id, store_id, artifact_kind, validation_status, collected_at
                FROM artifact_occurrence WHERE occurrence_id = :occurrence_id
                """,
                occurrence_id=occurrence_id,
            )
            if not identity_rows:
                raise ValueError(f"Occurrence {occurrence_id} does not exist.")
            chain_id, store_id, artifact_kind, validation_status, collected_at = identity_rows[0]
            if artifact_kind != "pricefull" or store_id is None:
                raise ValueError(
                    f"Occurrence {occurrence_id} is not a store-scoped 'pricefull' "
                    "occurrence; activate_occurrence only activates those."
                )
            if validation_status != "valid":
                raise ValueError(
                    f"Occurrence {occurrence_id} has validation_status "
                    f"{validation_status!r}, not 'valid'; a non-valid occurrence never "
                    "has derived state and must not be activated."
                )

            if normalized_items:
                for normalized_item in normalized_items:
                    if normalized_item.retailer_chain_id != chain_id:
                        raise ValueError(
                            f"NormalizedActivationItem.retailer_chain_id "
                            f"{normalized_item.retailer_chain_id!r} does not match occurrence "
                            f"{occurrence_id}'s chain_id {chain_id!r}."
                        )
                    if normalized_item.resolved_store_id != store_id:
                        raise ValueError(
                            f"NormalizedActivationItem.resolved_store_id "
                            f"{normalized_item.resolved_store_id!r} does not match occurrence "
                            f"{occurrence_id}'s store_id {store_id!r}."
                        )
                    if normalized_item.collected_at != collected_at:
                        raise ValueError(
                            f"NormalizedActivationItem.collected_at "
                            f"{normalized_item.collected_at!r} does not match occurrence "
                            f"{occurrence_id}'s collected_at {collected_at!r}."
                        )

            conn.run(
                "SELECT store_id FROM store WHERE store_id = :store_id FOR UPDATE",
                store_id=store_id,
            )

            resolved_rows = conn.run(
                "SELECT activation_completed_at FROM artifact_occurrence "
                "WHERE occurrence_id = :occurrence_id",
                occurrence_id=occurrence_id,
            )
            if resolved_rows[0][0] is not None:
                outcome = ActivationOutcome.ALREADY_APPLIED
            else:
                earlier_unresolved = conn.run(
                    """
                    SELECT occurrence_id FROM artifact_occurrence
                    WHERE chain_id = :chain_id AND store_id = :store_id
                      AND artifact_kind = 'pricefull' AND validation_status = 'valid'
                      AND activation_completed_at IS NULL
                      AND occurrence_id != :occurrence_id
                      AND (collected_at, occurrence_id) < (:collected_at, :occurrence_id)
                    LIMIT 1
                    """,
                    chain_id=chain_id,
                    store_id=store_id,
                    occurrence_id=occurrence_id,
                    collected_at=collected_at,
                )
                if earlier_unresolved:
                    raise _DeferredError

                later_resolved = conn.run(
                    """
                    SELECT occurrence_id FROM artifact_occurrence
                    WHERE chain_id = :chain_id AND store_id = :store_id
                      AND artifact_kind = 'pricefull' AND validation_status = 'valid'
                      AND activation_completed_at IS NOT NULL
                      AND (collected_at, occurrence_id) > (:collected_at, :occurrence_id)
                    LIMIT 1
                    """,
                    chain_id=chain_id,
                    store_id=store_id,
                    occurrence_id=occurrence_id,
                    collected_at=collected_at,
                )
                if later_resolved:
                    conn.run(
                        "UPDATE artifact_occurrence SET activation_completed_at = now(), "
                        "activation_outcome = :activation_outcome "
                        "WHERE occurrence_id = :occurrence_id",
                        activation_outcome=ActivationOutcome.STALE_PRESERVED.value,
                        occurrence_id=occurrence_id,
                    )
                    outcome = ActivationOutcome.STALE_PRESERVED
                else:
                    for index, item in enumerate(effective_items):
                        if on_checkpoint is not None:
                            on_checkpoint(_CHECKPOINT_BEFORE_CURRENT_STATE, index)

                        existing_price = _current_price(
                            conn,
                            chain_id=chain_id,
                            store_id=store_id,
                            item_code_raw=item.item_code_raw,
                        )
                        if item.normalized is None:
                            conn.run(
                                """
                                INSERT INTO store_product_current_state (
                                    chain_id, store_id, item_code_raw, current_price,
                                    current_price_raw, source_occurrence_id, updated_at
                                ) VALUES (
                                    :chain_id, :store_id, :item_code_raw, :price, :price_raw,
                                    :occurrence_id, :collected_at
                                )
                                ON CONFLICT (chain_id, store_id, item_code_raw) DO UPDATE SET
                                    current_price = excluded.current_price,
                                    current_price_raw = excluded.current_price_raw,
                                    source_occurrence_id = excluded.source_occurrence_id,
                                    updated_at = excluded.updated_at
                                """,
                                chain_id=chain_id,
                                store_id=store_id,
                                item_code_raw=item.item_code_raw,
                                price=item.price,
                                price_raw=item.price_raw,
                                occurrence_id=occurrence_id,
                                collected_at=collected_at,
                            )
                        else:
                            normalized = item.normalized
                            conn.run(
                                """
                                INSERT INTO store_product_current_state (
                                    chain_id, store_id, item_code_raw, current_price,
                                    current_price_raw, source_occurrence_id, updated_at,
                                    product_name, declared_quantity, declared_quantity_raw,
                                    declared_quantity_unit_raw, is_weighted,
                                    normalization_contract_version
                                ) VALUES (
                                    :chain_id, :store_id, :item_code_raw, :price, :price_raw,
                                    :occurrence_id, :collected_at,
                                    :product_name, :declared_quantity, :declared_quantity_raw,
                                    :declared_quantity_unit_raw, :is_weighted,
                                    :normalization_contract_version
                                )
                                ON CONFLICT (chain_id, store_id, item_code_raw) DO UPDATE SET
                                    current_price = excluded.current_price,
                                    current_price_raw = excluded.current_price_raw,
                                    source_occurrence_id = excluded.source_occurrence_id,
                                    updated_at = excluded.updated_at,
                                    product_name = excluded.product_name,
                                    declared_quantity = excluded.declared_quantity,
                                    declared_quantity_raw = excluded.declared_quantity_raw,
                                    declared_quantity_unit_raw =
                                        excluded.declared_quantity_unit_raw,
                                    is_weighted = excluded.is_weighted,
                                    normalization_contract_version =
                                        excluded.normalization_contract_version
                                """,
                                chain_id=chain_id,
                                store_id=normalized.resolved_store_id,
                                item_code_raw=item.item_code_raw,
                                price=item.price,
                                price_raw=item.price_raw,
                                occurrence_id=occurrence_id,
                                collected_at=collected_at,
                                product_name=normalized.product_name,
                                declared_quantity=normalized.declared_quantity,
                                declared_quantity_raw=normalized.declared_quantity_raw,
                                declared_quantity_unit_raw=normalized.declared_quantity_unit_raw,
                                is_weighted=normalized.is_weighted,
                                normalization_contract_version=1,
                            )

                        if on_checkpoint is not None:
                            on_checkpoint(_CHECKPOINT_AFTER_CURRENT_STATE, index)

                        if existing_price is None or existing_price != item.price:
                            conn.run(
                                """
                                INSERT INTO price_history (
                                    chain_id, store_id, item_code_raw, price, price_raw,
                                    observed_at, source_occurrence_id
                                ) VALUES (
                                    :chain_id, :store_id, :item_code_raw, :price, :price_raw,
                                    :collected_at, :occurrence_id
                                )
                                ON CONFLICT (source_occurrence_id, chain_id, item_code_raw)
                                DO NOTHING
                                """,
                                chain_id=chain_id,
                                store_id=store_id,
                                item_code_raw=item.item_code_raw,
                                price=item.price,
                                price_raw=item.price_raw,
                                collected_at=collected_at,
                                occurrence_id=occurrence_id,
                            )

                        if on_checkpoint is not None:
                            on_checkpoint(_CHECKPOINT_AFTER_PRICE_HISTORY, index)

                    if on_checkpoint is not None:
                        on_checkpoint(_CHECKPOINT_BEFORE_COMPLETION, -1)

                    conn.run(
                        "UPDATE artifact_occurrence SET activation_completed_at = now(), "
                        "activation_outcome = :activation_outcome "
                        "WHERE occurrence_id = :occurrence_id",
                        activation_outcome=ActivationOutcome.APPLIED.value,
                        occurrence_id=occurrence_id,
                    )
                    outcome = ActivationOutcome.APPLIED
    except _DeferredError:
        return ActivationOutcome.DEFERRED
    return outcome


def activation_status(conn: pg8000.native.Connection, occurrence_id: int) -> datetime | None:
    """Test/inspection helper: this occurrence's activation_completed_at,
    or None if it is still unresolved."""
    rows = conn.run(
        "SELECT activation_completed_at FROM artifact_occurrence "
        "WHERE occurrence_id = :occurrence_id",
        occurrence_id=occurrence_id,
    )
    if not rows:
        return None
    value: datetime | None = rows[0][0]
    return value


def activation_outcome(conn: pg8000.native.Connection, occurrence_id: int) -> str | None:
    """Test/inspection helper: this occurrence's durable activation_outcome
    ("applied" or "stale_preserved"), or None if it is still unresolved.
    Always non-None exactly when activation_status() is non-None -- the
    database CHECK constraint added in migration 0003 makes the opposite
    combination unrepresentable."""
    rows = conn.run(
        "SELECT activation_outcome FROM artifact_occurrence WHERE occurrence_id = :occurrence_id",
        occurrence_id=occurrence_id,
    )
    if not rows:
        return None
    value: str | None = rows[0][0]
    return value
