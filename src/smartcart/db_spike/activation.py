"""Minimal shapes for StoreProductCurrentState / PriceHistory.

Round 1 only proves these tables can hold data and reference their
originating occurrence atomically as a pair. It deliberately does NOT
implement:

- ordered activation across occurrences for the same (chain_id, store_id)
  (Fixed Data Invariant 5.B: (collected_at, occurrence_id) ordering),
- the stale-occurrence policy (Fixed Data Invariant 6),
- an idempotency/effect marker preventing the same occurrence from being
  activated twice,
- any cross-occurrence concurrency control.

All of that is Round 2. `record_price_observation` below performs only
the "at minimum" atomic pairing described by Fixed Data Invariant 7 for
ONE observation in isolation: the current-state upsert and the
price-history insert commit together or not at all. It is not a
substitute for Round 2's ordered/idempotent activation mechanism, and
must not be mistaken for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

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
