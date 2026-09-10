"""PID-T01/T02 (Batch A) and PID-T03/T04/T05/T38 (Batch B) -- Product
Identity Slice-A.

PID-T01 (characterization, expected GREEN): (chain_id, item_code_raw) is
the existing Retailer Tracking Identity -- chain_product's actual
PRIMARY KEY -- not a SmartCart Product ID. This test only inspects the
already-migrated schema; it creates no new Product Identity schema.

PID-T02 (GREEN): a SmartCart Product can be created with its own
SmartCart-owned Product ID, independent of any retailer tracking
identity, via the approved Slice-A seam
smartcart.db_spike.product_identity.create_product. This test does not
seed or require a chain_product row before creating the Product, and it
asserts the created Product is actually persisted in the approved
smartcart_product table boundary (product_id, display_name) -- not
merely that an arbitrary integer was returned.

Batch B (PID-T03, T04, T05-A/B/C, T38, expected RED): exercise the
approved-but-not-yet-implemented assign_chain_product/product_assignment
seam and the approved-but-not-yet-created chain_product_current_assignment
table boundary (chain_id, item_code_raw, product_id; PK (chain_id,
item_code_raw); FK (chain_id, item_code_raw) -> chain_product; FK
product_id -> smartcart_product; no UNIQUE(product_id)). None of that
production behavior or schema exists yet -- these tests express the
desired end state and are expected to fail for that reason, uncaught.

T38 assigns its two Tracking Identities to DIFFERENT chains
(CHAIN_A/ITEM_A and CHAIN_B/ITEM_B), staying within the approved
cross-retailer many->one boundary already covered by PID-T03; it does not
assert same-retailer many->one, which is outside the frozen evidence
boundary.

Two additional schema-boundary FK guard tests verify the
chain_product_current_assignment foreign keys by referenced table AND
referenced columns, not merely that some foreign key exists:
(chain_id, item_code_raw) -> chain_product(chain_id, item_code_raw), and
product_id -> smartcart_product(product_id). PID-T05-A stays focused on
its existing PRIMARY KEY assertion only; no separate NO UNIQUE(product_id)
schema test is added here, since PID-T03 already behaviorally protects
that requirement.

The tracking-identity FK guard is further strengthened to prove the exact
ordered pairwise mapping (chain_id -> chain_product.chain_id,
item_code_raw -> chain_product.item_code_raw) via
position_in_unique_constraint/ordinal_position, not just that each column
name appears somewhere in the FK's referencing/referenced column sets.
The single-column product_id -> smartcart_product(product_id) guard is
unchanged. PID-T05-C is strengthened to also assert that the exception
raised on conflicting reassignment is not NotImplementedError -- so an
unimplemented conflict path cannot accidentally satisfy the rejection
contract -- without freezing any specific exception type or message; this
new assertion is not yet reached, since the test still fails earlier at
the initial K -> A call while assign_chain_product remains unimplemented.

Batch C (PID-T39, T41, T42, T50, T53 -- frozen contract, docs/work-log.md
WL-0032): exercises the approved-but-not-yet-implemented
set_product_display_name() seam and the already-implemented Batch-B
assignment seam together. PID-T39/T50 are expected RED (the operation
under test calls set_product_display_name() directly, uncaught --
today's call raises NotImplementedError, which fails the test). PID-T41/
T42/T53 are immediate-GREEN characterization tests: they prove properties
that already hold given the current schema (display_name has no UNIQUE
constraint, product_id is an independent PK) and the current
implementation (assign_chain_product/product_assignment never reference
display_name) -- they are not weakened or invented merely to be GREEN.

PID-T42/T50 use real retailer current-state product_name evidence,
persisted through the existing, already-implemented normalized-activation
path (activate_occurrence + NormalizedActivationItem, Schema Slice 2 /
ADR 0011) -- never simulated via direct SQL -- and the real Batch-B
assign_chain_product()/product_assignment() seam for tracking->Product
linkage. Only the SmartCart Display Name itself is arranged via direct
SQL in PID-T41/T42/T53, where setter behavior is explicitly not what the
test protects; PID-T39/T50 call set_product_display_name() for the
operation under test and never substitute direct SQL for it. Neither
PID-T42 nor PID-T50 tests or claims successive same-source name history --
only the CURRENT retailer-reported name. No Display Name NULL/removal
transition is tested anywhere in Batch C; the setter contract remains
display_name: str. PID-T42 uses two DIFFERENT chains (cross-retailer,
PID-T03's already-approved boundary), not same-retailer many->one, which
remains UNKNOWN.

Slice B (PID-T07, PID-T40, GUARD-NO-CURRENT, GUARD-NOOP,
GUARD-ATOMICITY x2, HISTORY-PK-GUARD, HISTORY-TRACKING-FK-GUARD,
HISTORY-PRODUCT-FK-GUARD -- frozen contract, docs/work-log.md WL-0034 --
expected RED): exercises the approved-but-not-yet-implemented
correct_chain_product_assignment() seam and the approved-but-not-yet-
created chain_product_assignment_history table. The seam is resolved at
runtime via the product_identity module and getattr()
(_correct_chain_product_assignment below), never a top-level name-import
and never a static module-attribute reference, so collection succeeds
even though the function does not exist yet -- each behavioral test
fails naturally with AttributeError at the operation under test, the
same "call it directly and let the real error propagate" style Batch B/C
already established for NotImplementedError. getattr() is used (rather
than a direct product_identity.correct_chain_product_assignment
reference) specifically so mypy --strict does not statically require the
seam to exist yet. PID-T07 uses a two-correction (A->B->C) shape
because a single correction cannot distinguish true append-only history
from a mutable "previous assignment" slot -- both would leave exactly one
history row after only one correction. GUARD-ATOMICITY is one
parametrized test producing two pytest items (failure after real
mutation #1, and after real mutation #2), using pytest-side monkeypatching
of db_conn.run() -- no production on_checkpoint or other test hook is
added. No test uses a nonexistent target product_id, since
target-not-found behavior is explicitly not defined by the Slice-B
contract. The two schema-boundary FK guards and the PK guard follow the
same information_schema conventions already used for
chain_product_current_assignment above.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pg8000.native
import pytest

from smartcart.db_spike import product_identity
from smartcart.db_spike.activation import NormalizedActivationItem, activate_occurrence
from smartcart.db_spike.catalog import (
    get_or_create_store_by_alias,
    upsert_chain,
    upsert_chain_product,
    upsert_subchain,
)
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import insert_occurrence
from smartcart.db_spike.product_identity import (
    assign_chain_product,
    create_product,
    product_assignment,
    set_product_display_name,
)


def _seed_tracking_identity(
    conn: pg8000.native.Connection, *, chain_id: str, item_code_raw: str
) -> None:
    """Minimal Retailer Tracking Identity seed: a chain and one
    chain_product row for it. Mirrors the existing catalog.py public
    upsert helpers only -- no new seeding logic."""
    upsert_chain(conn, chain_id=chain_id, chain_name=None)
    upsert_chain_product(conn, chain_id=chain_id, item_code_raw=item_code_raw)


def _smartcart_product_count(conn: pg8000.native.Connection) -> int:
    rows = conn.run("SELECT count(*) FROM smartcart_product")
    count: int = rows[0][0]
    return count


def test_chain_product_primary_key_is_chain_id_and_item_code_raw(
    db_conn: pg8000.native.Connection,
) -> None:
    rows = db_conn.run(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'chain_product'
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
    )
    assert [row[0] for row in rows] == ["chain_id", "item_code_raw"]


def test_create_product_persists_a_smartcart_owned_product(
    db_conn: pg8000.native.Connection,
) -> None:
    product_id = create_product(db_conn)

    rows = db_conn.run(
        "SELECT product_id, display_name FROM smartcart_product WHERE product_id = :product_id",
        product_id=product_id,
    )
    assert len(rows) == 1
    assert rows[0][0] == product_id
    assert rows[0][1] is None


# --- Batch B ----------------------------------------------------------------


def test_pid_t03_cross_retailer_tracking_identities_may_assign_to_same_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """Two tracking identities belonging to two DIFFERENT chains may both
    be assigned to the same SmartCart Product (cross-retailer many->one).
    Display Name is not involved."""
    product_id = create_product(db_conn)
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    _seed_tracking_identity(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B")

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )
    assign_chain_product(
        db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B", product_id=product_id
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_id
    assert product_assignment(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B") == product_id


def test_pid_t04_unresolved_tracking_identity_has_no_assignment_and_creates_no_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """A real Tracking Identity that was never assigned is UNRESOLVED:
    product_assignment returns None, and merely querying it must not
    silently create a SmartCart Product."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    before_count = _smartcart_product_count(db_conn)

    result = product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")

    assert result is None
    assert _smartcart_product_count(db_conn) == before_count


def test_pid_t05a_chain_product_current_assignment_primary_key_is_chain_id_and_item_code_raw(
    db_conn: pg8000.native.Connection,
) -> None:
    """The approved chain_product_current_assignment table's PRIMARY KEY
    is exactly (chain_id, item_code_raw) -- the database cannot hold two
    simultaneous current-assignment rows for the same Tracking Identity.
    The table does not exist yet, so no PK columns are found."""
    rows = db_conn.run(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_current_assignment'
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
    )
    assert [row[0] for row in rows] == ["chain_id", "item_code_raw"]


def test_pid_t05b_identical_assignment_is_idempotent(
    db_conn: pg8000.native.Connection,
) -> None:
    """Assigning the same Tracking Identity to the same Product twice is
    an idempotent no-op: exactly one current-assignment row exists
    afterward, and product_assignment still reports that Product."""
    product_id = create_product(db_conn)
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )

    rows = db_conn.run(
        "SELECT product_id FROM chain_product_current_assignment "
        "WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw",
        chain_id="CHAIN_A",
        item_code_raw="ITEM_A",
    )
    assert len(rows) == 1
    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_id


def test_pid_t05c_conflicting_reassignment_is_rejected(
    db_conn: pg8000.native.Connection,
) -> None:
    """Once a Tracking Identity is assigned to Product A, assigning it to
    a DIFFERENT Product B must be rejected (a normal Exception, class not
    frozen -- no specific exception type or message is required) and must
    not replace the original assignment. The rejection must not be
    satisfiable merely by the seam still being unimplemented: the raised
    exception must not be NotImplementedError. Today this assertion is
    not yet reached -- the test still fails earlier, at the initial K -> A
    call, because assign_chain_product itself is unimplemented."""
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    with pytest.raises(Exception) as exc_info:
        assign_chain_product(
            db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_b
        )
    assert not isinstance(exc_info.value, NotImplementedError)

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_a


def test_pid_t38_additional_tracking_identity_does_not_change_product_id(
    db_conn: pg8000.native.Connection,
) -> None:
    """Assigning a second Tracking Identity, belonging to a DIFFERENT
    chain, to an existing Product does not change that Product's ID and
    creates no additional SmartCart Product as a side effect. The two
    Tracking Identities deliberately belong to different chains so this
    stays within the approved cross-retailer many->one boundary (PID-T03)
    -- it does not assert or exercise same-retailer many->one, which is
    not part of the frozen evidence boundary."""
    product_id = create_product(db_conn)
    before_count = _smartcart_product_count(db_conn)
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    _seed_tracking_identity(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B")

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )
    assign_chain_product(
        db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B", product_id=product_id
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_id
    assert product_assignment(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B") == product_id
    assert _smartcart_product_count(db_conn) == before_count


# --- Batch B schema-boundary FK guards --------------------------------------


def test_chain_product_current_assignment_fk_tracking_identity_references_chain_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """chain_product_current_assignment carries a FOREIGN KEY whose
    referencing/referenced columns pair up EXACTLY and POSITIONALLY:
    chain_id -> chain_product.chain_id and item_code_raw ->
    chain_product.item_code_raw -- not merely that each column name
    appears somewhere in the FK's column sets (which set equality alone
    cannot rule out a mismatched cross-pairing). This does not freeze the
    constraint name or any generated index name -- constraint_name is
    used only as an opaque join key between the referencing and
    referenced sides, via information_schema's own
    position_in_unique_constraint / ordinal_position columns, which
    Postgres populates without any naming convention. The table does not
    exist yet, so no matching FK is found and no pairs are returned."""
    rows = db_conn.run(
        """
        SELECT
            kcu_ref.column_name AS referencing_column,
            kcu_target.table_name AS referenced_table,
            kcu_target.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu_ref
          ON tc.constraint_name = kcu_ref.constraint_name
          AND tc.table_schema = kcu_ref.table_schema
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_name = rc.constraint_name
          AND tc.table_schema = rc.constraint_schema
        JOIN information_schema.key_column_usage kcu_target
          ON rc.unique_constraint_name = kcu_target.constraint_name
          AND rc.unique_constraint_schema = kcu_target.table_schema
          AND kcu_ref.position_in_unique_constraint = kcu_target.ordinal_position
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_current_assignment'
          AND kcu_target.table_name = 'chain_product'
        ORDER BY kcu_ref.ordinal_position
        """
    )
    pairs = [(row[0], row[2]) for row in rows]
    referenced_tables = {row[1] for row in rows}

    assert pairs == [("chain_id", "chain_id"), ("item_code_raw", "item_code_raw")]
    assert referenced_tables == {"chain_product"}


def test_chain_product_current_assignment_fk_product_id_references_smartcart_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """chain_product_current_assignment's product_id column carries a
    FOREIGN KEY that references smartcart_product(product_id) exactly --
    not merely that some foreign key exists on the table. The table does
    not exist yet, so no matching FK is found and the returned column sets
    are empty."""
    rows = db_conn.run(
        """
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
          AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_current_assignment'
          AND ccu.table_name = 'smartcart_product'
        """
    )
    referencing_columns = {row[0] for row in rows}
    referenced_tables = {row[1] for row in rows}
    referenced_columns = {row[2] for row in rows}

    assert referencing_columns == {"product_id"}
    assert referenced_tables == {"smartcart_product"}
    assert referenced_columns == {"product_id"}


# --- Batch C helpers ---------------------------------------------------------


def _set_display_name_directly(
    conn: pg8000.native.Connection, *, product_id: int, display_name: str
) -> None:
    """Direct-SQL arrangement of smartcart_product.display_name, used only
    in PID-T41/T42/T53, where Display Name SETTER behavior is not what the
    test protects -- never a substitute for set_product_display_name()
    itself (PID-T39/T50 call the real setter for the operation under
    test)."""
    conn.run(
        "UPDATE smartcart_product SET display_name = :display_name WHERE product_id = :product_id",
        product_id=product_id,
        display_name=display_name,
    )


def _seed_retailer_source_name(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    item_code_raw: str,
    source_name: str,
) -> None:
    """Persist one real retailer current-state product_name via the
    existing, already-implemented normalized activation path
    (activate_occurrence + NormalizedActivationItem, Schema Slice 2 / ADR
    0011) -- never simulated via direct SQL. Mirrors
    tests/db_spike/round2_support.py's seeding conventions, parameterized
    by chain_id so PID-T42 can use two different chains. Also establishes
    the chain_product row this chain_id/item_code_raw Tracking Identity
    needs for a later assign_chain_product() call."""
    subchain_id = "SUB"
    upsert_chain(conn, chain_id=chain_id, chain_name=None)
    upsert_subchain(conn, chain_id=chain_id, subchain_id=subchain_id, subchain_name=None)
    store_id = get_or_create_store_by_alias(
        conn,
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="test",
        alias_context="filename_store_id",
        raw_value="1",
    )
    upsert_chain_product(conn, chain_id=chain_id, item_code_raw=item_code_raw)

    collected_at_value = datetime(2026, 1, 1, tzinfo=UTC)
    payload = f"<Root>{chain_id}:{item_code_raw}:{source_name}:{id(object())}</Root>".encode()
    content = insert_or_get_content(conn, payload)
    occurrence = insert_occurrence(
        conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=chain_id,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull_test.xml",
        schema_family=None,
        collected_at=collected_at_value,
        validation_status="valid",
    )
    activate_occurrence(
        conn,
        occurrence_id=occurrence.occurrence_id,
        products=(),
        normalized_items=[
            NormalizedActivationItem(
                retailer_chain_id=chain_id,
                resolved_store_id=store_id,
                item_code_raw=item_code_raw,
                price=Decimal("1.00"),
                price_raw="1.00",
                product_name=source_name,
                declared_quantity=Decimal("1"),
                declared_quantity_raw="1",
                declared_quantity_unit_raw="unit",
                is_weighted=False,
                collected_at=collected_at_value,
            )
        ],
    )


def _retailer_product_name(
    conn: pg8000.native.Connection, *, chain_id: str, item_code_raw: str
) -> str | None:
    """Test/inspection helper: the CURRENT retailer-reported product_name
    for one Tracking Identity, read directly from
    store_product_current_state -- there is no history to read; only the
    current value."""
    rows = conn.run(
        "SELECT product_name FROM store_product_current_state "
        "WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw",
        chain_id=chain_id,
        item_code_raw=item_code_raw,
    )
    if not rows:
        return None
    name: str | None = rows[0][0]
    return name


# --- Batch C ------------------------------------------------------------------


def test_pid_t39_changing_display_name_does_not_change_product_id(
    db_conn: pg8000.native.Connection,
) -> None:
    """Changing the SmartCart Display Name does not change the Product's
    ID. The operation under test goes through the real
    set_product_display_name() seam, never a direct SQL update -- today
    this fails at the first real call because that seam is still
    NotImplementedError. No Display Name NULL/removal transition is
    tested."""
    product_id = create_product(db_conn)
    before_count = _smartcart_product_count(db_conn)

    set_product_display_name(db_conn, product_id=product_id, display_name="First Name")
    set_product_display_name(db_conn, product_id=product_id, display_name="Second Name")

    rows = db_conn.run(
        "SELECT product_id, display_name FROM smartcart_product WHERE product_id = :product_id",
        product_id=product_id,
    )
    assert rows[0][0] == product_id
    assert rows[0][1] == "Second Name"
    assert _smartcart_product_count(db_conn) == before_count


def test_pid_t41_two_products_may_share_an_identical_display_name(
    db_conn: pg8000.native.Connection,
) -> None:
    """Two distinct SmartCart Products may have the same non-null Display
    Name and remain distinct Products -- display_name carries no UNIQUE
    constraint (migration 0005) and product_id is an independent PK, so
    this already holds today. Display Name is arranged directly via SQL
    because setter behavior is not what this test protects."""
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    _set_display_name_directly(db_conn, product_id=product_a, display_name="Shared Name")
    _set_display_name_directly(db_conn, product_id=product_b, display_name="Shared Name")

    rows = db_conn.run(
        "SELECT product_id, display_name FROM smartcart_product "
        "WHERE product_id IN (:product_a, :product_b) ORDER BY product_id",
        product_a=product_a,
        product_b=product_b,
    )

    assert product_a != product_b
    assert [row[0] for row in rows] == sorted([product_a, product_b])
    assert all(row[1] == "Shared Name" for row in rows)


def test_pid_t42_retailer_source_names_coexist_independently_with_display_name(
    db_conn: pg8000.native.Connection,
) -> None:
    """Current retailer source-observed names coexist independently
    alongside the SmartCart Display Name for the SAME resolved Product.
    Uses two DIFFERENT chains (cross-retailer, PID-T03's already-approved
    boundary) -- this does not assert or exercise same-retailer
    many->one. Source names are persisted through the real,
    already-implemented normalized activation path, never simulated via
    direct SQL; both Tracking Identities are assigned to the same Product
    through the real Batch-B assign_chain_product() seam. Only the
    SmartCart Display Name is arranged directly via SQL, since setter
    behavior is not what this test protects. This does not test or claim
    successive same-source name history -- only the CURRENT
    retailer-reported name for each chain."""
    _seed_retailer_source_name(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", source_name="Source Name A"
    )
    _seed_retailer_source_name(
        db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B", source_name="Source Name B"
    )
    product_id = create_product(db_conn)

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )
    assign_chain_product(
        db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B", product_id=product_id
    )
    _set_display_name_directly(db_conn, product_id=product_id, display_name="SmartCart Name")

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_id
    assert product_assignment(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B") == product_id
    assert (
        _retailer_product_name(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
        == "Source Name A"
    )
    assert (
        _retailer_product_name(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B")
        == "Source Name B"
    )

    rows = db_conn.run(
        "SELECT display_name FROM smartcart_product WHERE product_id = :product_id",
        product_id=product_id,
    )
    assert rows[0][0] == "SmartCart Name"


def test_pid_t50_changing_display_name_does_not_mutate_id_assignment_or_source_name(
    db_conn: pg8000.native.Connection,
) -> None:
    """Changing an already-set SmartCart Display Name must not change
    Product ID, must not change the existing tracking->Product
    assignment, and must not mutate the retailer current-state source
    name used in this scenario. Uses a real retailer current-state
    product_name (via the real normalized activation path) and a real
    Batch-B assignment; the Display Name change itself goes through the
    real set_product_display_name() seam, never simulated via SQL. Today
    this fails at the FIRST real setter call because that seam is still
    NotImplementedError -- the later non-mutation assertions are not yet
    reached. Once the setter is implemented, this SAME test must proceed
    through both setter calls and reach every assertion below; it must
    not be weakened later merely to make it pass. No Display Name
    NULL/removal transition is tested."""
    _seed_retailer_source_name(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", source_name="Original Source Name"
    )
    product_id = create_product(db_conn)
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_id
    )

    set_product_display_name(db_conn, product_id=product_id, display_name="Initial Name")
    set_product_display_name(db_conn, product_id=product_id, display_name="Changed Name")

    rows = db_conn.run(
        "SELECT product_id, display_name FROM smartcart_product WHERE product_id = :product_id",
        product_id=product_id,
    )
    assert rows[0][0] == product_id
    assert rows[0][1] == "Changed Name"
    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_id
    assert (
        _retailer_product_name(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
        == "Original Source Name"
    )


def test_pid_t53_identity_linkage_is_name_independent(
    db_conn: pg8000.native.Connection,
) -> None:
    """Identity linkage is name-independent: two DIFFERENT Tracking
    Identities assigned to two DIFFERENT Products that happen to share an
    identical Display Name each still resolve, through
    product_assignment(), to their own correct Product -- an identical
    Display Name does not drive or collapse the authoritative linkage.
    Uses different chains to remain clear of the same-retailer many->one
    open question. Display Name is arranged directly via SQL because
    setter behavior is not what this test protects; the assignments
    themselves go through the real assign_chain_product() seam, never
    simulated via SQL."""
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    _set_display_name_directly(db_conn, product_id=product_a, display_name="Shared Name")
    _set_display_name_directly(db_conn, product_id=product_b, display_name="Shared Name")
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    _seed_tracking_identity(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B")

    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )
    assign_chain_product(
        db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B", product_id=product_b
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_a
    assert product_assignment(db_conn, chain_id="CHAIN_B", item_code_raw="ITEM_B") == product_b


# --- Slice B helpers ----------------------------------------------------------


def _assignment_history_rows(
    conn: pg8000.native.Connection, *, chain_id: str, item_code_raw: str
) -> list[tuple[int, int, object]]:
    """Test/inspection helper: (assignment_history_id, product_id,
    superseded_at) rows for one Tracking Identity's assignment history, in
    deterministic append order. No production history-read API exists;
    this is a direct SQL read, mirroring this file's existing convention
    (e.g. _retailer_product_name)."""
    rows = conn.run(
        "SELECT assignment_history_id, product_id, superseded_at "
        "FROM chain_product_assignment_history "
        "WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw "
        "ORDER BY assignment_history_id",
        chain_id=chain_id,
        item_code_raw=item_code_raw,
    )
    return [(row[0], row[1], row[2]) for row in rows]


def _correct_chain_product_assignment(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    item_code_raw: str,
    product_id: int,
) -> None:
    """Resolves and calls the future, approved
    _correct_chain_product_assignment() seam at runtime
    via getattr -- never a static attribute/name reference -- so mypy
    does not require the seam to exist yet, and collection succeeds even
    though it doesn't. Adds no logic of its own: raises AttributeError,
    uncaught, exactly as a direct product_identity.correct_chain_product_assignment(...)
    call would, if the seam is not yet implemented."""
    getattr(  # noqa: B009 -- deliberate dynamic resolution so mypy does not require the not-yet-implemented seam to exist
        product_identity, "correct_chain_product_assignment"
    )(conn, chain_id=chain_id, item_code_raw=item_code_raw, product_id=product_id)


def _fail_after_nth_mutation(
    real_run: Callable[..., object], *, fail_after: int
) -> Callable[..., object]:
    """Returns a conn.run() replacement that executes every statement for
    real, then raises immediately after the fail_after-th real mutating
    (INSERT/UPDATE) statement succeeds. BEGIN/SELECT/ROLLBACK pass through
    untouched. Order-independent: it counts mutating statements by SQL
    text as they actually execute, not by a hardcoded position, so it
    proves atomicity regardless of which write the correction seam issues
    first."""
    count = 0

    def flaky_run(sql: str, **kwargs: object) -> object:
        nonlocal count
        result = real_run(sql, **kwargs)
        if sql.strip().upper().startswith(("INSERT", "UPDATE")):
            count += 1
            if count == fail_after:
                raise RuntimeError(f"injected failure after real mutation #{fail_after}")
        return result

    return flaky_run


# --- Slice B --------------------------------------------------------------


def test_pid_t07_correction_is_append_only_and_preserves_superseded_history(
    db_conn: pg8000.native.Connection,
) -> None:
    """A->B then B->C: each correction makes the new Product current and
    appends -- never overwrites -- a history row for the Product it
    superseded. The two-correction shape is required to prove append-only
    behavior; a single correction cannot distinguish "append a new row"
    from "overwrite a mutable previous-assignment slot", since both would
    leave exactly one history row after only one correction. The
    operation under test goes through the real, approved
    correct_chain_product_assignment() seam, resolved at runtime via the
    product_identity module -- never a direct name-import, since the
    function does not exist yet. No exact timestamp value or wall-clock
    ordering is asserted -- only that superseded_at is non-null and that
    the captured value for the A row is unchanged after the second
    correction."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    product_c = create_product(db_conn)
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    _correct_chain_product_assignment(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_b
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_b
    history_after_first = _assignment_history_rows(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A"
    )
    assert len(history_after_first) == 1
    first_history_id, first_product_id, first_superseded_at = history_after_first[0]
    assert first_product_id == product_a
    assert first_superseded_at is not None

    _correct_chain_product_assignment(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_c
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_c
    history_after_second = _assignment_history_rows(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A"
    )
    assert len(history_after_second) == 2
    assert history_after_second[0] == (first_history_id, product_a, first_superseded_at)
    assert history_after_second[0][0] < history_after_second[1][0]
    assert history_after_second[1][1] == product_b
    assert history_after_second[1][2] is not None

    product_rows = db_conn.run(
        "SELECT product_id FROM smartcart_product WHERE product_id IN (:a, :b, :c)",
        a=product_a,
        b=product_b,
        c=product_c,
    )
    assert {row[0] for row in product_rows} == {product_a, product_b, product_c}
    tracking_rows = db_conn.run(
        "SELECT chain_id, item_code_raw FROM chain_product "
        "WHERE chain_id = :chain_id AND item_code_raw = :item_code_raw",
        chain_id="CHAIN_A",
        item_code_raw="ITEM_A",
    )
    assert len(tracking_rows) == 1


def test_pid_t40_correction_does_not_change_display_names(
    db_conn: pg8000.native.Connection,
) -> None:
    """A real correction (A->B) must not alter either Product's SmartCart
    Display Name -- Display Name belongs to the Product, not to the
    tracking->Product link, and is never derived or refreshed from
    retailer/source names by a correction."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    set_product_display_name(db_conn, product_id=product_a, display_name="Name A")
    set_product_display_name(db_conn, product_id=product_b, display_name="Name B")
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    _correct_chain_product_assignment(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_b
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_b
    rows = db_conn.run(
        "SELECT product_id, display_name FROM smartcart_product "
        "WHERE product_id IN (:a, :b) ORDER BY product_id",
        a=product_a,
        b=product_b,
    )
    display_names = {row[0]: row[1] for row in rows}
    assert display_names[product_a] == "Name A"
    assert display_names[product_b] == "Name B"


def test_guard_no_current_assignment_correction_is_rejected(
    db_conn: pg8000.native.Connection,
) -> None:
    """Correcting a Tracking Identity that has no current authoritative
    assignment is rejected with ValueError (message not frozen) -- it
    must not behave like a first assignment. After rejection, K remains
    UNRESOLVED and no history row is created. Uses a real, existing
    target Product -- target-not-found behavior is explicitly not part of
    this Slice-B contract."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    product_b = create_product(db_conn)

    with pytest.raises(ValueError):
        _correct_chain_product_assignment(
            db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_b
        )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") is None
    assert _assignment_history_rows(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == []


def test_guard_idempotent_correction_to_same_product_is_a_noop(
    db_conn: pg8000.native.Connection,
) -> None:
    """Explicit correction requesting the SAME Product a Tracking Identity
    is already assigned to succeeds as an idempotent no-op: current
    remains unchanged and no history row is created -- this is not a
    supersession event."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    product_a = create_product(db_conn)
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    _correct_chain_product_assignment(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_a
    assert _assignment_history_rows(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == []


@pytest.mark.parametrize("fail_after_mutation", [1, 2])
def test_guard_atomicity_failure_after_real_mutation_rolls_back(
    db_conn: pg8000.native.Connection,
    monkeypatch: pytest.MonkeyPatch,
    fail_after_mutation: int,
) -> None:
    """A genuine failure injected immediately after either the first or
    the second real mutating statement of a correction leaves the
    database exactly as it was before the correction was attempted: A
    remains current, and no superseded-A history row persists. Proves the
    two-write correction (history-insert + current-update) is atomic
    regardless of which write happens first or second -- the injection
    point is chosen by counting real mutating statements as they execute,
    not by assuming a fixed write order. No production on_checkpoint or
    other test hook is added; only this one test's own db_conn.run is
    wrapped via pytest's monkeypatch, and the real, already-approved
    transaction(conn) rollback path is what actually undoes the
    mutation."""
    _seed_tracking_identity(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A")
    product_a = create_product(db_conn)
    product_b = create_product(db_conn)
    assign_chain_product(
        db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_a
    )

    real_run = db_conn.run
    monkeypatch.setattr(
        db_conn, "run", _fail_after_nth_mutation(real_run, fail_after=fail_after_mutation)
    )

    with pytest.raises(RuntimeError, match="injected failure"):
        _correct_chain_product_assignment(
            db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A", product_id=product_b
        )

    assert product_assignment(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == product_a
    assert _assignment_history_rows(db_conn, chain_id="CHAIN_A", item_code_raw="ITEM_A") == []


def test_chain_product_assignment_history_primary_key_is_assignment_history_id(
    db_conn: pg8000.native.Connection,
) -> None:
    """chain_product_assignment_history's PRIMARY KEY is exactly
    assignment_history_id -- the durable monotonic history-row identity.
    The table does not exist yet, so no PK columns are found."""
    rows = db_conn.run(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_assignment_history'
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
    )
    assert [row[0] for row in rows] == ["assignment_history_id"]


def test_chain_product_assignment_history_fk_tracking_identity_references_chain_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """chain_product_assignment_history carries a FOREIGN KEY whose
    referencing/referenced columns pair up EXACTLY and POSITIONALLY:
    chain_id -> chain_product.chain_id and item_code_raw ->
    chain_product.item_code_raw. The table does not exist yet, so no
    matching FK is found and no pairs are returned."""
    rows = db_conn.run(
        """
        SELECT
            kcu_ref.column_name AS referencing_column,
            kcu_target.table_name AS referenced_table,
            kcu_target.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu_ref
          ON tc.constraint_name = kcu_ref.constraint_name
          AND tc.table_schema = kcu_ref.table_schema
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_name = rc.constraint_name
          AND tc.table_schema = rc.constraint_schema
        JOIN information_schema.key_column_usage kcu_target
          ON rc.unique_constraint_name = kcu_target.constraint_name
          AND rc.unique_constraint_schema = kcu_target.table_schema
          AND kcu_ref.position_in_unique_constraint = kcu_target.ordinal_position
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_assignment_history'
          AND kcu_target.table_name = 'chain_product'
        ORDER BY kcu_ref.ordinal_position
        """
    )
    pairs = [(row[0], row[2]) for row in rows]
    referenced_tables = {row[1] for row in rows}

    assert pairs == [("chain_id", "chain_id"), ("item_code_raw", "item_code_raw")]
    assert referenced_tables == {"chain_product"}


def test_chain_product_assignment_history_fk_product_id_references_smartcart_product(
    db_conn: pg8000.native.Connection,
) -> None:
    """chain_product_assignment_history.product_id carries a FOREIGN KEY
    that references smartcart_product(product_id) exactly. The table
    does not exist yet, so no matching FK is found and the returned
    column sets are empty."""
    rows = db_conn.run(
        """
        SELECT kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
          AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
          AND tc.table_name = 'chain_product_assignment_history'
          AND ccu.table_name = 'smartcart_product'
        """
    )
    referencing_columns = {row[0] for row in rows}
    referenced_tables = {row[1] for row in rows}
    referenced_columns = {row[2] for row in rows}

    assert referencing_columns == {"product_id"}
    assert referenced_tables == {"smartcart_product"}
    assert referenced_columns == {"product_id"}
