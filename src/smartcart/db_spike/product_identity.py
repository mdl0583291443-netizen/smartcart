"""Product Identity Slice-A: Batch-A, Batch-B, and Batch-C (Display Name
setter) foundation.

create_product (Batch A) persists one SmartCart-owned Product row
(migration 0005) and returns its product_id, requiring no retailer/chain/
item_code_raw input and leaving display_name NULL.

assign_chain_product/product_assignment (Batch B) implement the approved
seam over chain_product_current_assignment (migration 0006): the current,
authoritative assignment of a Retailer Tracking Identity (chain_id,
item_code_raw) to a SmartCart Product ID. No assignment row means
UNRESOLVED. product_id is not UNIQUE -- cross-retailer many->one
assignment is allowed; same-retailer many->one remains UNKNOWN and is
neither asserted nor exercised here. Assigning an already-assigned
Tracking Identity to a DIFFERENT Product is rejected with ValueError --
this package's established convention for rejected/invalid persistence
state (see db_spike/activation.py) -- and leaves the existing assignment
unchanged; assigning it to the SAME Product again is an idempotent no-op.

set_product_display_name (Batch C) writes the supplied display_name to an
existing Product's smartcart_product.display_name row -- nothing else.
Display Name is explicitly NOT Product identity: this call never touches
product_id, chain_product_current_assignment, or any retailer/source
current-state evidence, all of which remain exactly as they were before
the call. No naming algorithm, no preservation of prior Display Name
values, and no NULL/removal transition are introduced here -- the
setter's public contract remains display_name: str.

correct_chain_product_assignment (Slice B) deliberately corrects a
Tracking Identity's current assignment to a different Product, over the
append-only chain_product_assignment_history table (migration 0007): no
current assignment to correct is rejected with ValueError -- this is not
a first assignment, which remains assign_chain_product's responsibility;
a request for the already-current Product is an idempotent no-op with no
history row; a genuine correction appends the superseded Product to
history and updates the current assignment, atomically (both happen or
neither does). History rows are append-only -- never updated or deleted
-- so a second correction leaves an earlier correction's history row
unchanged. assign_chain_product's own semantics (including its rejection
of a conflicting reassignment, still protected by PID-T05-C) are
unchanged by this seam's existence; the two are separate, deliberately
non-overlapping entry points. Display Name, retailer/source current-state
evidence, and chain_product/smartcart_product themselves are never
touched by a correction. Behavior for a requested product_id that does
not exist is not part of this Slice-B contract -- whatever the database's
own constraints produce for that case is not a documented API guarantee.

No resolver logic, no candidate/confidence model, no GTIN verification,
no naming algorithm, and no source-name history mechanism are present in
this file.
"""

from __future__ import annotations

import pg8000.native

from smartcart.db_spike.db import transaction


def create_product(conn: pg8000.native.Connection) -> int:
    rows = conn.run("INSERT INTO smartcart_product DEFAULT VALUES RETURNING product_id")
    product_id: int = rows[0][0]
    return product_id


def set_product_display_name(
    conn: pg8000.native.Connection,
    *,
    product_id: int,
    display_name: str,
) -> None:
    """Set an existing Product's SmartCart Display Name.

    Writes only smartcart_product.display_name for the given product_id.
    Does not touch product_id, chain_product_current_assignment, or any
    retailer/source current-state evidence.
    """
    conn.run(
        "UPDATE smartcart_product SET display_name = :display_name WHERE product_id = :product_id",
        product_id=product_id,
        display_name=display_name,
    )


def assign_chain_product(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    item_code_raw: str,
    product_id: int,
) -> None:
    """Assign a Retailer Tracking Identity to a SmartCart Product.

    No existing assignment: persists the new assignment. Identical
    existing assignment (same product_id): idempotent no-op. Conflicting
    existing assignment (a different product_id): rejected with
    ValueError; the existing assignment is left unchanged.
    """
    with transaction(conn):
        existing = conn.run(
            """
            SELECT product_id FROM chain_product_current_assignment
            WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw
            """,
            chain_id=chain_id,
            item_code_raw=item_code_raw,
        )
        if existing:
            existing_product_id: int = existing[0][0]
            if existing_product_id != product_id:
                raise ValueError(
                    f"Tracking Identity (chain_id={chain_id!r}, "
                    f"item_code_raw={item_code_raw!r}) is already assigned to "
                    f"Product {existing_product_id}; refusing to reassign it to "
                    f"Product {product_id}. Assignment correction is a separate, "
                    "not-yet-implemented concern (Slice B)."
                )
            return
        conn.run(
            """
            INSERT INTO chain_product_current_assignment (chain_id, item_code_raw, product_id)
            VALUES (:chain_id, :item_code_raw, :product_id)
            """,
            chain_id=chain_id,
            item_code_raw=item_code_raw,
            product_id=product_id,
        )


def product_assignment(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    item_code_raw: str,
) -> int | None:
    """Return the current SmartCart Product ID assigned to a Retailer
    Tracking Identity, or None if UNRESOLVED (no assignment exists).
    Read-only: never creates or modifies anything."""
    rows = conn.run(
        """
        SELECT product_id FROM chain_product_current_assignment
        WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw
        """,
        chain_id=chain_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    product_id: int = rows[0][0]
    return product_id


def correct_chain_product_assignment(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    item_code_raw: str,
    product_id: int,
) -> None:
    """Deliberately correct a Tracking Identity's current assignment to a
    different SmartCart Product.

    No current assignment: rejected with ValueError -- correction is not
    a first assignment (see assign_chain_product for that). Requested
    product_id already current: idempotent no-op, no history row.
    Genuine correction: the previously-current Product is appended to
    chain_product_assignment_history and the current assignment becomes
    product_id, atomically.
    """
    with transaction(conn):
        existing = conn.run(
            """
            SELECT product_id FROM chain_product_current_assignment
            WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw
            """,
            chain_id=chain_id,
            item_code_raw=item_code_raw,
        )
        if not existing:
            raise ValueError(
                f"Tracking Identity (chain_id={chain_id!r}, "
                f"item_code_raw={item_code_raw!r}) has no current assignment to "
                "correct; correction is not a first assignment."
            )
        existing_product_id: int = existing[0][0]
        if existing_product_id == product_id:
            return

        conn.run(
            """
            INSERT INTO chain_product_assignment_history
                (chain_id, item_code_raw, product_id, superseded_at)
            VALUES (:chain_id, :item_code_raw, :product_id, now())
            """,
            chain_id=chain_id,
            item_code_raw=item_code_raw,
            product_id=existing_product_id,
        )
        conn.run(
            """
            UPDATE chain_product_current_assignment
            SET product_id = :product_id
            WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw
            """,
            chain_id=chain_id,
            item_code_raw=item_code_raw,
            product_id=product_id,
        )
