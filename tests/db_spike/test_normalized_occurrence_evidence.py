"""SmartCart Ingestion TDD -- T13 Slice A, RED-1 and RED-13 ONLY.

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

Explicitly NOT asserted by either test in this file (later RED tests, not
these):
- RED-2: evidence durability when projection activation is DEFERRED.
- RED-3: idempotent/non-duplicating persistence on replay.
- RED-4: two distinct provenance dimensions (shared contract version vs.
  transformation-behavior provenance).
- RED-5: evidence surviving independently of deleted CurrentState/
  PriceHistory.
- Any Slice B (rebuild) or Slice C (publication) behavior.

(Semantic item-sequence preservation (RED-1) and occurrence/item agreement
fail-closed rejection (RED-13) ARE in scope for this file -- both are
properties of the persist/read seam itself, not a later slice's concern.)

Does NOT target `activate_occurrence()` as the evidence-creation API, per
the frozen T13 design: evidence persistence is a seam of its own.
"""

from __future__ import annotations

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
