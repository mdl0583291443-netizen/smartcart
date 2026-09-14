"""RED tests for the approved Promotions Stage-1 normalization contract
(`smartcart.normalize.promotion_contract`) and its two occurrence-level
entry points (`smartcart.normalize.promotion`).

`normalize_standard_promotions_occurrence` and
`normalize_online_promotions_occurrence` are fully implemented today for
the pre-Group-preservation contract shape (2-tuple return,
StandardMembershipFacts carrying min_no_of_item_offered_raw, no Group
concept). This file now also encodes the FROZEN Group-preservation target
contract (SG-01..SG-15, Group-preservation test matrix SG-T01..SG-T11):
Standard gains a Group layer (`NormalizedPromotionGroup`,
`StandardGroupFacts`, `group_index` on memberships), MinNoOfItemOffered
relocates from StandardMembershipFacts to StandardPromotionFacts, and
`normalize_standard_promotions_occurrence` changes its return arity to a
3-tuple `(promotions, groups, memberships)`. None of this exists in
production yet -- every test exercising it is expected to be RED, for one
of two clean, attributable reasons:

- calling `normalize_standard_promotions_occurrence` and unpacking its
  return into three names raises `ValueError: not enough values to unpack`
  today, because the function still returns a 2-tuple; this is the RED
  reason for nearly every Standard-family test in this file, including
  ones (T-A, T-C, T-D, etc.) whose own behavioral point predates Group
  preservation entirely -- they still must unpack the frozen 3-tuple shape
  to stay forward-consistent with the target contract;
- accessing `.group_index` on a `NormalizedPromotionMembership`, or
  importing `NormalizedPromotionGroup`/`StandardGroupFacts` from
  `smartcart.normalize.promotion_contract`, fails today because neither
  exists in production yet. Those two names are deliberately imported
  LOCALLY, inside only the specific test functions that need them (T-G/
  SG-T01, SG-T02) -- never at module level -- so that importing them does
  not collapse the ENTIRE file's collection into one undifferentiated
  ImportError and mask every other test's own, more specific RED reason.

Online-family tests are unaffected except SG-T11, which specifically
proves `group_index is None` on Online memberships -- Online's own 2-tuple
return and existing economics stay exactly as before.

`raw` is test-local, ad hoc nested dicts only -- never a new production
dataclass. The skeleton's public signature accepts `raw: object`
specifically because no Promotions raw parser contract has been designed
yet (that remains out of scope here); inventing one now, even test-only,
would freeze an unjustified production parser API.
`_standard_occurrence`/`_online_occurrence` below are the sole, centralized
construction point for that synthetic nesting -- TEST SCAFFOLDING ONLY.
`_standard_occurrence`'s internal shape now nests items under
`groups[].items` (previously a flat `items` list directly under each
promotion) to mechanically mirror the frozen Promotion -> Group ->
Membership target; it still does not attempt to mirror the real XML's
exact tag names, and must never be read as the future real parser/XML DTO
-- that remains a separate, not-yet-made design decision. `_online_occurrence`
is unchanged: Online has no Group concept in the frozen target.

T-G is the one exception among the pre-existing tests: it inspects the
already-real dataclasses in `promotion_contract.py` directly (no call to
either entry point). Its original six assertions exercise already-existing
production code and remain GREEN; the two new assertions it gains for
SG-T01 (StandardGroupFacts, NormalizedPromotionGroup field-set pins) go RED
via the local-import mechanism described above.

T-Q..T-T (Phase 2, failure semantics) wrap their call in
`pytest.raises(ValueError)` rather than leaving it uncaught, and do not
unpack the return value at all -- they remain GREEN, unaffected by the
return-arity change, since the underlying malformed-input `ValueError` they
were already proving still fires before any return value would ever be
constructed.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from smartcart.normalize.promotion import (
    normalize_online_promotions_occurrence,
    normalize_standard_promotions_occurrence,
)
from smartcart.normalize.promotion_contract import (
    NormalizedPromotion,
    NormalizedPromotionMembership,
    OnlineMembershipFacts,
    OnlinePromotionFacts,
    StandardMembershipFacts,
    StandardPromotionFacts,
)

_COLLECTED_AT = datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC)

# A distinctive, unmistakable timestamp for T-O's pass-through proof --
# deliberately not reused anywhere else in this file, so a test failure
# that shows this exact value can only mean it leaked from the wrong place.
_DISTINCTIVE_COLLECTED_AT = datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC)

_STANDARD_CHAIN_ID = "7290027600007"  # real Shufersal GLN, already used elsewhere in this repo
_STANDARD_STORE_ID = "756"

_ONLINE_CHAIN_ID = "7290058140886"  # real Rami Levy GLN, already used elsewhere in this repo
_ONLINE_STORE_ID = "039"


# ---------------------------------------------------------------------------
# Synthetic raw-input builders (TEST SCAFFOLDING ONLY -- see module
# docstring). Exactly two family-level builders own all synthetic raw
# nesting for this file; no per-promotion/per-item sub-builders exist, and
# none of this shape is a production parser DTO.
# ---------------------------------------------------------------------------

_OMIT = object()
"""Sentinel: a test wants this key genuinely ABSENT from the built raw
dict -- distinct from a present key whose value is "". Needed for Phase 2's
"required field is genuinely missing" fixtures (T-R/S/T) and for SG-T05's
genuinely-missing-GroupID fixture. TEST-ONLY, never a production parser DTO
concept.
"""


def _standard_occurrence(
    *,
    chain_id: object = _STANDARD_CHAIN_ID,
    store_id: object = _STANDARD_STORE_ID,
    promotions: list[dict[str, object]],
) -> dict[str, object]:
    """Assemble a synthetic Standard-family Promotions occurrence.

    `promotions` is a list of plain dicts, one per promotion. Each may
    supply any of the promotion-level keys (promotion_id, description,
    start_at, end_at, is_gift_item, min_no_of_item_offered) plus a
    "groups" list of plain per-group dicts (group_id, discount_type,
    min_purchase_amount) each carrying its own "items" list of plain
    per-item dicts (item_code, reward_type, discount_rate,
    discounted_price, min_qty, max_qty). Any key a caller omits falls back
    to an inert empty-string default, so a call site only needs to state
    the field(s) relevant to what it's testing. Passing `_OMIT` (for
    chain_id/store_id, or as any promotion-/group-/item-level field's
    value) removes that key from the built dict entirely instead of
    defaulting it, for fixtures that need genuine absence rather than "".

    min_no_of_item_offered moved here (promotion level) from the former
    per-item default, mirroring the frozen Group-preservation target's
    real-evidence-verified source placement -- see SG-T09.
    """
    promotion_defaults = {
        "promotion_id": "",
        "description": "",
        "start_at": "",
        "end_at": "",
        "is_gift_item": "",
        "min_no_of_item_offered": "",
    }
    group_defaults = {
        "group_id": "",
        "discount_type": "",
        "min_purchase_amount": "",
    }
    item_defaults = {
        "item_code": "",
        "reward_type": "",
        "discount_rate": "",
        "discounted_price": "",
        "min_qty": "",
        "max_qty": "",
    }
    built_promotions = []
    for promo in promotions:
        groups = []
        for group in promo.get("groups", []):
            items = []
            for item in group.get("items", []):
                merged_item = {**item_defaults, **item}
                items.append({k: v for k, v in merged_item.items() if v is not _OMIT})
            merged_group = {
                **group_defaults,
                **{k: v for k, v in group.items() if k != "items"},
            }
            built_group = {k: v for k, v in merged_group.items() if v is not _OMIT}
            built_group["items"] = items
            groups.append(built_group)
        merged_promo = {
            **promotion_defaults,
            **{k: v for k, v in promo.items() if k != "groups"},
        }
        built_promo = {k: v for k, v in merged_promo.items() if v is not _OMIT}
        built_promo["groups"] = groups
        built_promotions.append(built_promo)
    envelope: dict[str, object] = {"promotions": built_promotions}
    if chain_id is not _OMIT:
        envelope["chain_id"] = chain_id
    if store_id is not _OMIT:
        envelope["store_id"] = store_id
    return envelope


def _online_occurrence(
    *,
    chain_id: object = _ONLINE_CHAIN_ID,
    store_id: object = _ONLINE_STORE_ID,
    promotions: list[dict[str, object]],
) -> dict[str, object]:
    """Assemble a synthetic Online-family Promotions occurrence.

    `promotions` is a list of plain dicts, one per promotion. Each may
    supply any of the promotion-level keys (promotion_id, description,
    start_at, end_at, reward_type, discount_type, discount_rate,
    discounted_price, discounted_price_per_mida, min_qty,
    min_no_of_item_offered, max_qty) plus an "items" list of plain
    per-item dicts (item_code, is_gift_item, item_type). Any key a caller
    omits falls back to an inert empty-string default. Passing `_OMIT` (see
    `_standard_occurrence`) removes that key entirely instead of defaulting
    it. Unchanged from before Group preservation: Online has no Group
    concept in the frozen target.
    """
    promotion_defaults = {
        "promotion_id": "",
        "description": "",
        "start_at": "",
        "end_at": "",
        "reward_type": "",
        "discount_type": "",
        "discount_rate": "",
        "discounted_price": "",
        "discounted_price_per_mida": "",
        "min_qty": "",
        "min_no_of_item_offered": "",
        "max_qty": "",
    }
    item_defaults = {
        "item_code": "",
        "is_gift_item": "",
        "item_type": "",
    }
    built_promotions = []
    for promo in promotions:
        items = []
        for item in promo.get("items", []):
            merged_item = {**item_defaults, **item}
            items.append({k: v for k, v in merged_item.items() if v is not _OMIT})
        merged_promo = {**promotion_defaults, **{k: v for k, v in promo.items() if k != "items"}}
        built_promo = {k: v for k, v in merged_promo.items() if v is not _OMIT}
        built_promo["items"] = items
        built_promotions.append(built_promo)
    envelope: dict[str, object] = {"promotions": built_promotions}
    if chain_id is not _OMIT:
        envelope["chain_id"] = chain_id
    if store_id is not _OMIT:
        envelope["store_id"] = store_id
    return envelope


# ---------------------------------------------------------------------------
# T-A -- Standard happy path
# ---------------------------------------------------------------------------

_STANDARD_MINIMAL_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "4586297",
            "description": "20₪ קופון חברתי",
            "start_at": "2026-08-02 00:00",
            "end_at": "2026-10-03 23:59",
            "is_gift_item": "0",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290121290494",
                            "reward_type": "3",
                            "discount_rate": "33",
                            "discounted_price": "10.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        }
    ],
)


def test_standard_happy_path_maps_minimal_occurrence_to_frozen_contract() -> None:
    """T-A: one promotion, one group, one membership, every frozen shared +
    Standard family field populated -- eventual success, exact raw
    mapping. min_no_of_item_offered_raw is asserted on StandardPromotionFacts
    only (SG-T09's relocation), not on the membership."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    promo = promotions[0]
    assert isinstance(promo, NormalizedPromotion)
    assert promo.promotion_id_raw == "4586297"
    assert promo.retailer_chain_id == _STANDARD_CHAIN_ID
    assert promo.store_id_raw == _STANDARD_STORE_ID
    assert promo.source_family == "standard"
    assert promo.description_raw == "20₪ קופון חברתי"
    assert promo.start_at_raw == "2026-08-02 00:00"
    assert promo.end_at_raw == "2026-10-03 23:59"
    assert promo.collected_at == _COLLECTED_AT
    assert isinstance(promo.family_facts, StandardPromotionFacts)
    assert promo.family_facts.is_gift_item_raw == "0"
    assert promo.family_facts.min_no_of_item_offered_raw == "1"

    assert len(memberships) == 1
    member = memberships[0]
    assert isinstance(member, NormalizedPromotionMembership)
    assert member.promotion_id_raw == "4586297"
    assert member.retailer_item_id_raw == "7290121290494"
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.reward_type_raw == "3"
    assert member.family_facts.discount_rate_raw == "33"
    assert member.family_facts.discounted_price_raw == "10.00"
    assert member.family_facts.min_qty_raw == "1"
    assert member.family_facts.max_qty_raw == "0"


# ---------------------------------------------------------------------------
# T-B -- Online happy path
# ---------------------------------------------------------------------------

_ONLINE_MINIMAL_OCCURRENCE = _online_occurrence(
    promotions=[
        {
            "promotion_id": "910370783",
            "description": 'שוקולד לינדט ב-19.90 ש"ח',
            "start_at": "2026-08-02T00:00:00",
            "end_at": "2026-10-03T23:59:00",
            "reward_type": "1",
            "discount_type": "1",
            "discount_rate": "0",
            "discounted_price": "19.90",
            "discounted_price_per_mida": "19.90",
            "min_qty": "1",
            "min_no_of_item_offered": "0",
            "max_qty": "0",
            "items": [
                {
                    "item_code": "3046920023047",
                    "is_gift_item": "0",
                    "item_type": "1",
                }
            ],
        }
    ],
)


def test_online_happy_path_maps_minimal_occurrence_to_frozen_contract() -> None:
    """T-B: same pattern as T-A for the Online family, covering every
    OnlinePromotionFacts and OnlineMembershipFacts field. Unaffected by
    Group preservation -- Online stays a 2-tuple."""
    promotions, memberships = normalize_online_promotions_occurrence(
        _ONLINE_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    promo = promotions[0]
    assert isinstance(promo, NormalizedPromotion)
    assert promo.promotion_id_raw == "910370783"
    assert promo.retailer_chain_id == _ONLINE_CHAIN_ID
    assert promo.store_id_raw == _ONLINE_STORE_ID
    assert promo.source_family == "online"
    assert promo.collected_at == _COLLECTED_AT
    assert isinstance(promo.family_facts, OnlinePromotionFacts)
    assert promo.family_facts.reward_type_raw == "1"
    assert promo.family_facts.discount_type_raw == "1"
    assert promo.family_facts.discount_rate_raw == "0"
    assert promo.family_facts.discounted_price_raw == "19.90"
    assert promo.family_facts.discounted_price_per_mida_raw == "19.90"
    assert promo.family_facts.min_qty_raw == "1"
    assert promo.family_facts.min_no_of_item_offered_raw == "0"
    assert promo.family_facts.max_qty_raw == "0"

    assert len(memberships) == 1
    member = memberships[0]
    assert isinstance(member, NormalizedPromotionMembership)
    assert member.promotion_id_raw == "910370783"
    assert member.retailer_item_id_raw == "3046920023047"
    assert isinstance(member.family_facts, OnlineMembershipFacts)
    assert member.family_facts.is_gift_item_raw == "0"
    assert member.family_facts.item_type_raw == "1"


# ---------------------------------------------------------------------------
# T-C -- one promotion -> multiple memberships
# ---------------------------------------------------------------------------

_STANDARD_ONE_PROMOTION_THREE_ITEMS = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417604",
            "description": "עוגיות טוסו",
            "start_at": "2026-08-01",
            "end_at": "2026-09-01",
            "is_gift_item": "",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290016319187",
                            "reward_type": "3",
                            "discount_rate": "25",
                            "discounted_price": "14.90",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "7290016319194",
                            "reward_type": "3",
                            "discount_rate": "25",
                            "discounted_price": "14.90",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "7290016319200",
                            "reward_type": "3",
                            "discount_rate": "25",
                            "discounted_price": "14.90",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                }
            ],
        }
    ],
)


def test_one_promotion_with_three_skus_yields_one_promotion_and_three_memberships() -> None:
    """T-C: one occurrence, one promotion, three distinct participating
    SKUs -- one NormalizedPromotion, three NormalizedPromotionMembership,
    all linked to the same promotion_id_raw."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_ONE_PROMOTION_THREE_ITEMS, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    assert promotions[0].promotion_id_raw == "0001417604"

    assert len(memberships) == 3
    assert {m.retailer_item_id_raw for m in memberships} == {
        "7290016319187",
        "7290016319194",
        "7290016319200",
    }
    assert {m.promotion_id_raw for m in memberships} == {"0001417604"}


# ---------------------------------------------------------------------------
# T-D -- one SKU in multiple promotions
# ---------------------------------------------------------------------------

_STANDARD_SAME_SKU_TWO_PROMOTIONS = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001411108",
            "description": "קופון פיצוי לקוח",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290014066373",
                            "reward_type": "1",
                            "discount_rate": "100",
                            "discounted_price": "0.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        },
        {
            "promotion_id": "0001421247",
            "description": "מבצע נוסף",
            "start_at": "2026-09-01",
            "end_at": "2026-09-30",
            "is_gift_item": "",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290014066373",
                            "reward_type": "3",
                            "discount_rate": "15",
                            "discounted_price": "12.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        },
    ],
)


def test_same_sku_across_two_promotions_yields_two_distinct_memberships() -> None:
    """T-D: one occurrence, two promotions, the same retailer_item_id_raw
    appears under both -- two distinct memberships, same SKU identity,
    different promotion IDs, no accidental dedup/merge."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_SAME_SKU_TWO_PROMOTIONS, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 2
    assert len(memberships) == 2
    assert {m.retailer_item_id_raw for m in memberships} == {"7290014066373"}
    assert {m.promotion_id_raw for m in memberships} == {"0001411108", "0001421247"}
    # Each membership keeps its own promotion-scoped economics -- proves
    # they were not collapsed into one deduplicated-by-SKU record.
    by_promotion = {m.promotion_id_raw: m for m in memberships}
    assert by_promotion["0001411108"].family_facts.discounted_price_raw == "0.00"
    assert by_promotion["0001421247"].family_facts.discounted_price_raw == "12.00"


# ---------------------------------------------------------------------------
# T-E -- Standard economics stay membership-level
# ---------------------------------------------------------------------------


def test_standard_economics_land_on_membership_not_promotion_or_shared_envelope() -> None:
    """T-E: Standard item-level economic fields (RewardType, DiscountRate,
    DiscountedPrice, MinQty, MaxQty) must normalize into
    StandardMembershipFacts -- never onto StandardPromotionFacts or the
    shared NormalizedPromotion envelope. MinNoOfItemOffered is deliberately
    NOT in that list: per SG-T09, it is promotion-level, asserted there."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, StandardPromotionFacts)
    # StandardPromotionFacts' only declared fields are is_gift_item_raw and
    # min_no_of_item_offered_raw -- this is a positive assertion on the
    # actual value landing there, not a shape re-check (that's T-G's job).
    assert promo.family_facts.is_gift_item_raw == "0"

    member = memberships[0]
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.reward_type_raw == "3"
    assert member.family_facts.discount_rate_raw == "33"
    assert member.family_facts.discounted_price_raw == "10.00"
    assert member.family_facts.min_qty_raw == "1"
    assert member.family_facts.max_qty_raw == "0"


# ---------------------------------------------------------------------------
# T-F -- Online economics stay promotion-level
# ---------------------------------------------------------------------------


def test_online_economics_land_on_promotion_not_membership_or_shared_envelope() -> None:
    """T-F: Online economic fields must normalize into OnlinePromotionFacts
    -- never onto OnlineMembershipFacts or the shared envelope."""
    promotions, memberships = normalize_online_promotions_occurrence(
        _ONLINE_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, OnlinePromotionFacts)
    assert promo.family_facts.reward_type_raw == "1"
    assert promo.family_facts.discount_type_raw == "1"
    assert promo.family_facts.discount_rate_raw == "0"
    assert promo.family_facts.discounted_price_raw == "19.90"
    assert promo.family_facts.discounted_price_per_mida_raw == "19.90"
    assert promo.family_facts.min_qty_raw == "1"
    assert promo.family_facts.min_no_of_item_offered_raw == "0"
    assert promo.family_facts.max_qty_raw == "0"

    member = memberships[0]
    assert isinstance(member.family_facts, OnlineMembershipFacts)
    # OnlineMembershipFacts' only declared fields are identity/gift/type --
    # a positive value re-check, not a shape re-check (T-G covers shape).
    assert member.family_facts.is_gift_item_raw == "0"
    assert member.family_facts.item_type_raw == "1"


# ---------------------------------------------------------------------------
# T-G / SG-T01 -- exact positive contract shape / family isolation
# ---------------------------------------------------------------------------


def test_frozen_contract_shape_is_a_closed_positive_enumeration() -> None:
    """T-G / SG-T01: assert the frozen contract's exact field sets directly
    against the real dataclasses -- a closed positive enumeration, not a
    blacklist of forbidden field names. Absorbs the former T-V intent.

    This test does not call either normalize entry point, so its original
    six assertions are NOT subject to any skeleton/arity issue -- they
    exercise real, already-existing production code (the dataclass
    definitions themselves) and remain GREEN. It remains meaningful (not
    vacuous) because it pins the exact field set now, so any future
    accidental field addition/removal/rename on these types -- in either
    direction -- fails this test immediately, before any behavioral
    implementation exists to hide the drift.

    The two new SG-T01 assertions (StandardGroupFacts,
    NormalizedPromotionGroup) import those two names LOCALLY, inside this
    function, because neither exists in production yet -- a module-level
    import would fail collection for the entire file (see module
    docstring). Those two assertions are the ones expected to go RED here.
    """
    assert {f.name for f in dataclasses.fields(NormalizedPromotion)} == {
        "promotion_id_raw",
        "retailer_chain_id",
        "store_id_raw",
        "source_family",
        "description_raw",
        "start_at_raw",
        "end_at_raw",
        "collected_at",
        "family_facts",
    }
    assert {f.name for f in dataclasses.fields(NormalizedPromotionMembership)} == {
        "promotion_id_raw",
        "retailer_item_id_raw",
        "family_facts",
        "group_index",
    }
    assert {f.name for f in dataclasses.fields(StandardPromotionFacts)} == {
        "is_gift_item_raw",
        "min_no_of_item_offered_raw",
    }
    assert {f.name for f in dataclasses.fields(OnlinePromotionFacts)} == {
        "reward_type_raw",
        "discount_type_raw",
        "discount_rate_raw",
        "discounted_price_raw",
        "discounted_price_per_mida_raw",
        "min_qty_raw",
        "min_no_of_item_offered_raw",
        "max_qty_raw",
    }
    assert {f.name for f in dataclasses.fields(StandardMembershipFacts)} == {
        "reward_type_raw",
        "discount_rate_raw",
        "discounted_price_raw",
        "min_qty_raw",
        "max_qty_raw",
    }
    assert {f.name for f in dataclasses.fields(OnlineMembershipFacts)} == {
        "is_gift_item_raw",
        "item_type_raw",
    }

    from smartcart.normalize.promotion_contract import (
        NormalizedPromotionGroup,
        StandardGroupFacts,
    )

    assert {f.name for f in dataclasses.fields(StandardGroupFacts)} == {
        "group_id_raw",
        "discount_type_raw",
        "min_purchase_amount_raw",
    }
    assert {f.name for f in dataclasses.fields(NormalizedPromotionGroup)} == {
        "promotion_id_raw",
        "group_index",
        "family_facts",
    }


# ---------------------------------------------------------------------------
# T-H -- Standard IsGiftItem raw/non-boolean preservation
# ---------------------------------------------------------------------------

_STANDARD_NON_BOOLEAN_GIFT_FLAG_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "4586641",
            "description": "מתנה",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            # Real observed shape: Shufersal's IsGiftItem was seen as a
            # non-boolean value ("1.5") in prior recon, not just "0"/"1".
            "is_gift_item": "1.5",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "8006530264495",
                            "reward_type": "2",
                            "discount_rate": "100",
                            "discounted_price": "0.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        }
    ],
)


def test_standard_non_boolean_is_gift_item_is_preserved_raw_without_bool_coercion() -> None:
    """T-H: a non-boolean IsGiftItem source value ("1.5") must survive
    exactly as a string on StandardPromotionFacts -- never coerced to
    True/False, never rejected as invalid."""
    promotions, _groups, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_NON_BOOLEAN_GIFT_FLAG_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, StandardPromotionFacts)
    assert promo.family_facts.is_gift_item_raw == "1.5"
    assert not isinstance(promo.family_facts.is_gift_item_raw, bool)


# ---------------------------------------------------------------------------
# T-I -- Online IsGiftItem membership-level raw preservation
# ---------------------------------------------------------------------------

_ONLINE_NON_TRIVIAL_GIFT_FLAG_OCCURRENCE = _online_occurrence(
    promotions=[
        {
            "promotion_id": "412199",
            "description": "2+1 מתנה",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-31T23:59:00",
            "reward_type": "9",
            "discount_type": "1",
            "discount_rate": "0",
            "discounted_price": "0",
            "discounted_price_per_mida": "0",
            "min_qty": "3",
            "min_no_of_item_offered": "0",
            "max_qty": "0",
            "items": [
                {
                    "item_code": "7702018470884",
                    "is_gift_item": "2",
                    "item_type": "1",
                }
            ],
        }
    ],
)


def test_online_is_gift_item_is_preserved_raw_at_membership_level() -> None:
    """T-I: Online's IsGiftItem is membership-level (unlike Standard's
    promotion-level flag) and must survive exactly as a string on
    OnlineMembershipFacts, without bool coercion."""
    _promotions, memberships = normalize_online_promotions_occurrence(
        _ONLINE_NON_TRIVIAL_GIFT_FLAG_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    member = memberships[0]
    assert isinstance(member.family_facts, OnlineMembershipFacts)
    assert member.family_facts.is_gift_item_raw == "2"
    assert not isinstance(member.family_facts.is_gift_item_raw, bool)


# ---------------------------------------------------------------------------
# SG-T09 (supersedes former T-J) -- MinNoOfItemOffered relocation
# ---------------------------------------------------------------------------

_STANDARD_PROMOTION_LEVEL_MIN_NO_OF_ITEM_OFFERED_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001379851",
            "description": "מאגדת שלגונים",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            # Real observed placement (see prior recon): MinNoOfItemOffered
            # is a Promotion-level field in real Standard XML, not
            # PromotionItem-level.
            "min_no_of_item_offered": "10",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290002680178",
                            "reward_type": "3",
                            "discount_rate": "34.75",
                            "discounted_price": "16.90",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        }
    ],
)


def test_sg_t09_min_no_of_item_offered_lands_on_promotion_not_membership() -> None:
    """SG-T09 (supersedes former T-J, whose premise -- comparing MinQty and
    MinNoOfItemOffered as two independent membership-level fields -- no
    longer holds once MinNoOfItemOffered relocates to Promotion level): the
    real, evidence-verified source placement of MinNoOfItemOffered is
    Promotion-level, not PromotionItem-level. It must land on
    StandardPromotionFacts.min_no_of_item_offered_raw,
    StandardMembershipFacts must no longer carry any such field at all, and
    the value must not be duplicated onto any membership."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_PROMOTION_LEVEL_MIN_NO_OF_ITEM_OFFERED_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert promo.family_facts.min_no_of_item_offered_raw == "10"

    member = memberships[0]
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert not hasattr(member.family_facts, "min_no_of_item_offered_raw")
    assert member.family_facts.min_qty_raw == "1"


# ---------------------------------------------------------------------------
# T-K -- DiscountedPrice raw preservation
# ---------------------------------------------------------------------------

_ONLINE_BUNDLE_TOTAL_DISCOUNTED_PRICE_OCCURRENCE = _online_occurrence(
    promotions=[
        {
            "promotion_id": "910399999",
            "description": "2 יח' ב-90 ש\"ח",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-31T23:59:00",
            "reward_type": "1",
            "discount_type": "1",
            "discount_rate": "0",
            # Real observed shape from prior recon: for a "2 units for 90"
            # bundle, DiscountedPrice is the BUNDLE TOTAL (90), not a
            # per-unit price -- exactly the value that could tempt a wrong
            # "effective unit price" interpretation.
            "discounted_price": "90",
            "discounted_price_per_mida": "45",
            "min_qty": "2",
            "min_no_of_item_offered": "0",
            "max_qty": "0",
            "items": [{"item_code": "3046920099999", "is_gift_item": "0", "item_type": "1"}],
        }
    ],
)


def test_discounted_price_is_preserved_raw_without_deriving_an_effective_price() -> None:
    """T-K: DiscountedPrice ("90", a bundle total that could tempt a wrong
    per-unit interpretation) must be preserved exactly as the raw source
    string. No effective/per-unit price is asserted or derived here."""
    promotions, _memberships = normalize_online_promotions_occurrence(
        _ONLINE_BUNDLE_TOTAL_DISCOUNTED_PRICE_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, OnlinePromotionFacts)
    assert promo.family_facts.discounted_price_raw == "90"
    assert promo.family_facts.discounted_price_per_mida_raw == "45"


# ---------------------------------------------------------------------------
# T-L -- unknown RewardType is valid opaque data
# ---------------------------------------------------------------------------

_STANDARD_UNKNOWN_REWARD_TYPE_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0009999999",
            "description": "מבצע לא מזוהה",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290099999999",
                            # Unrecognized/never-before-observed RewardType value.
                            "reward_type": "99",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        }
    ],
)


def test_unknown_reward_type_normalizes_as_valid_opaque_data() -> None:
    """T-L: an unrecognized RewardType value ("99") must normalize
    successfully and round-trip unchanged -- unknown semantic meaning must
    NOT itself be modeled as malformed/rejected data."""
    _promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_UNKNOWN_REWARD_TYPE_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    member = memberships[0]
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.reward_type_raw == "99"


# ---------------------------------------------------------------------------
# T-M -- unknown DiscountType is valid opaque data (Online only)
# ---------------------------------------------------------------------------

_ONLINE_UNKNOWN_DISCOUNT_TYPE_OCCURRENCE = _online_occurrence(
    promotions=[
        {
            "promotion_id": "910399998",
            "description": "מבצע לא מזוהה",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-31T23:59:00",
            "reward_type": "1",
            # Unrecognized/never-before-observed DiscountType value.
            "discount_type": "9",
            "discount_rate": "0",
            "discounted_price": "50",
            "discounted_price_per_mida": "50",
            "min_qty": "1",
            "min_no_of_item_offered": "0",
            "max_qty": "0",
            "items": [{"item_code": "7290099999998", "is_gift_item": "0", "item_type": "1"}],
        }
    ],
)


def test_unknown_discount_type_normalizes_as_valid_opaque_data() -> None:
    """T-M: same principle as T-L, for Online's DiscountType field."""
    promotions, _memberships = normalize_online_promotions_occurrence(
        _ONLINE_UNKNOWN_DISCOUNT_TYPE_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, OnlinePromotionFacts)
    assert promo.family_facts.discount_type_raw == "9"


# ---------------------------------------------------------------------------
# T-N -- membership without PriceFull still normalizes
# ---------------------------------------------------------------------------
#
# No PriceFull fixture, record type, or module is imported anywhere in this
# file. That absence is itself the proof: promotion normalization at the
# public boundary cannot depend on same-store PriceFull presence, because
# nothing PriceFull-shaped is even reachable from this test.


def test_membership_normalizes_without_any_pricefull_input_or_dependency() -> None:
    """T-N: promotion normalization is independent of same-store PriceFull
    presence -- proved structurally (no PriceFull import anywhere in this
    file), not by inspecting internal calls."""
    promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    assert len(memberships) == 1


# ---------------------------------------------------------------------------
# T-O -- exact collected_at pass-through
# ---------------------------------------------------------------------------


def test_every_normalized_promotion_carries_the_exact_caller_supplied_collected_at() -> None:
    """T-O: a distinctive timezone-aware collected_at must appear,
    unmodified, on every NormalizedPromotion produced from the occurrence
    -- no regeneration, truncation, or timezone normalization."""
    promotions, _groups, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_SAME_SKU_TWO_PROMOTIONS, collected_at=_DISTINCTIVE_COLLECTED_AT
    )

    assert len(promotions) == 2
    for promo in promotions:
        assert promo.collected_at == _DISTINCTIVE_COLLECTED_AT
        assert promo.collected_at.tzinfo is not None


# ---------------------------------------------------------------------------
# T-P -- occurrence/source provenance boundary
# ---------------------------------------------------------------------------
#
# source_occurrence_id is deliberately NOT part of NormalizedPromotion (see
# promotion_contract.py) -- no test here reintroduces it. This test is
# deliberately narrower than it might first sound: T-A/T-B already assert
# retailer_chain_id/store_id_raw/source_family once each on a single-
# promotion fixture, T-G already pins the exact field set, and T-O already
# proves collected_at pass-through. What none of those cover is whether
# retailer_chain_id/store_id_raw/source_family remain the SAME correct
# scope facts on EVERY promotion produced from one multi-promotion
# occurrence (the same "does it hold across the whole list" question T-O
# asks for collected_at specifically) -- that is the one non-duplicative
# angle this test adds.


def test_every_normalized_promotion_carries_the_same_occurrence_scope_facts() -> None:
    """T-P: retailer_chain_id, store_id_raw, and source_family must remain
    sufficient, consistent source/scope facts across every
    NormalizedPromotion produced from one occurrence -- not just the first
    one, not defaulted or varied per-promotion."""
    promotions, _groups, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_SAME_SKU_TWO_PROMOTIONS, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 2
    for promo in promotions:
        assert promo.retailer_chain_id == _STANDARD_CHAIN_ID
        assert promo.store_id_raw == _STANDARD_STORE_ID
        assert promo.source_family == "standard"


# ===========================================================================
# GROUP PRESERVATION -- SG-T02..SG-T08, SG-T10, SG-T11
# (SG-T01 is T-G above; SG-T09 supersedes former T-J above)
# ===========================================================================


# ---------------------------------------------------------------------------
# SG-T02 -- single Standard Group
# ---------------------------------------------------------------------------

_STANDARD_ONE_GROUP_TWO_ITEMS_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417100",
            "description": "מארז שתיה",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "1",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "7290020000001",
                            "reward_type": "10",
                            "discount_rate": "",
                            "discounted_price": "10.00",
                            "min_qty": "2",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "7290020000002",
                            "reward_type": "10",
                            "discount_rate": "",
                            "discounted_price": "10.00",
                            "min_qty": "2",
                            "max_qty": "0",
                        },
                    ],
                }
            ],
        }
    ],
)


def test_sg_t02_single_standard_group_yields_one_group_and_two_memberships() -> None:
    """SG-T02: one Promotion, one Group, two items -- one NormalizedPromotion,
    one NormalizedPromotionGroup at group_index 0, two
    NormalizedPromotionMembership records both linked to that same
    group_index, all sharing the same promotion_id_raw. Raw Group facts
    (GroupID, DiscountType, MinPurchaseAmount) preserved exactly."""
    from smartcart.normalize.promotion_contract import (
        NormalizedPromotionGroup,
        StandardGroupFacts,
    )

    promotions, groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_ONE_GROUP_TWO_ITEMS_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    assert promotions[0].promotion_id_raw == "0001417100"

    assert len(groups) == 1
    group = groups[0]
    assert isinstance(group, NormalizedPromotionGroup)
    assert group.promotion_id_raw == "0001417100"
    assert group.group_index == 0
    assert isinstance(group.family_facts, StandardGroupFacts)
    assert group.family_facts.group_id_raw == "1"
    assert group.family_facts.discount_type_raw == "0"
    assert group.family_facts.min_purchase_amount_raw == "0.00"

    assert len(memberships) == 2
    assert {m.retailer_item_id_raw for m in memberships} == {
        "7290020000001",
        "7290020000002",
    }
    for member in memberships:
        assert member.promotion_id_raw == "0001417100"
        assert member.group_index == 0


# ---------------------------------------------------------------------------
# SG-T03 -- Carrefour structural counterexample
# ---------------------------------------------------------------------------

# STRUCTURAL EVIDENCE-DERIVED FIXTURE.
# The two-Group structure and [3,1] partition derive from the real Carrefour
# PromotionID 0011248601 observation.
# The ItemCode values below are test placeholders and are NOT transcribed
# retailer source values.
_STANDARD_CARREFOUR_TWO_GROUP_DISJOINT_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0011248601",
            "description": "מוצרי סויה וטופו",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "1",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9000000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "9000000000002",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "9000000000003",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
                {
                    "group_id": "2",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9000000000004",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t03_carrefour_two_group_disjoint_item_sets_remain_distinct() -> None:
    """SG-T03: real Carrefour structural counterexample (see fixture
    comment for exact evidence provenance) -- one PromotionID with two
    Groups carrying disjoint item sets must normalize into two distinct
    NormalizedPromotionGroup records at group_index 0 and 1, with each
    group's memberships remaining attached to their own source Group --
    never merged/collapsed into one."""
    _promotions, groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_CARREFOUR_TWO_GROUP_DISJOINT_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(groups) == 2
    assert [g.group_index for g in groups] == [0, 1]

    by_group_index = {
        0: {m.retailer_item_id_raw for m in memberships if m.group_index == 0},
        1: {m.retailer_item_id_raw for m in memberships if m.group_index == 1},
    }
    assert by_group_index[0] == {
        "9000000000001",
        "9000000000002",
        "9000000000003",
    }
    assert by_group_index[1] == {"9000000000004"}
    assert by_group_index[0].isdisjoint(by_group_index[1])


# ---------------------------------------------------------------------------
# SG-T04 -- duplicate GroupID
# ---------------------------------------------------------------------------

_STANDARD_DUPLICATE_GROUP_ID_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417200",
            "description": "שתי קבוצות עם אותו מזהה",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "1",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9100000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
                {
                    # Deliberate mutation: same group_id as the first Group,
                    # to prove raw GroupID is not treated as structural
                    # identity.
                    "group_id": "1",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9100000000002",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t04_duplicate_raw_group_id_still_yields_two_distinct_groups() -> None:
    """SG-T04: two Groups under one Promotion sharing the same raw
    group_id_raw ("1") must still normalize into two structurally distinct
    NormalizedPromotionGroup records at group_index 0 and 1 -- proving raw
    GroupID is not used as structural identity; group_index is."""
    _promotions, groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_DUPLICATE_GROUP_ID_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(groups) == 2
    assert [g.group_index for g in groups] == [0, 1]
    assert groups[0].family_facts.group_id_raw == "1"
    assert groups[1].family_facts.group_id_raw == "1"

    by_group_index = {m.group_index: m.retailer_item_id_raw for m in memberships}
    assert by_group_index[0] == "9100000000001"
    assert by_group_index[1] == "9100000000002"


# ---------------------------------------------------------------------------
# SG-T05 -- missing/empty GroupID
# ---------------------------------------------------------------------------

_STANDARD_MISSING_GROUP_ID_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417300",
            "description": "קבוצה ללא מזהה",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    # group_id genuinely absent from source (not merely an
                    # empty string) -- matches this file's existing _OMIT
                    # convention for "field genuinely missing".
                    "group_id": _OMIT,
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9200000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
                {
                    "group_id": "2",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9200000000002",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t05_missing_group_id_does_not_prevent_structural_distinction() -> None:
    """SG-T05: a Group with a genuinely absent raw GroupID must remain
    structurally distinct from its sibling Group -- group_index supplies
    structural linkage independently of GroupID; no identifier is invented
    for the missing value (it stays None, the same raw-absence convention
    used elsewhere in this file), and no validation rule rejects it."""
    _promotions, groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MISSING_GROUP_ID_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(groups) == 2
    assert [g.group_index for g in groups] == [0, 1]
    assert groups[0].family_facts.group_id_raw is None
    assert groups[1].family_facts.group_id_raw == "2"

    by_group_index = {m.group_index: m.retailer_item_id_raw for m in memberships}
    assert by_group_index[0] == "9200000000001"
    assert by_group_index[1] == "9200000000002"


# ---------------------------------------------------------------------------
# SG-T06 -- Group facts remain opaque
# ---------------------------------------------------------------------------

_STANDARD_GROUP_FACTS_OPAQUE_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417400",
            "description": "קבוצה עם ערכים גולמיים",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "1",
                    # Unrecognized/never-before-observed DiscountType value
                    # -- same "unknown value is valid opaque data"
                    # principle as T-L/T-M, applied to Group-level
                    # DiscountType.
                    "discount_type": "9",
                    "min_purchase_amount": "150.00",
                    "items": [
                        {
                            "item_code": "9300000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t06_group_facts_are_preserved_as_opaque_raw_strings() -> None:
    """SG-T06: GroupID, DiscountType, and MinPurchaseAmount must survive
    exactly as raw strings on StandardGroupFacts -- no enum interpretation,
    no economic interpretation, no semantic coercion, and an unrecognized
    DiscountType value ("9") normalizes successfully like any other opaque
    code (same principle as T-L/T-M)."""
    _promotions, groups, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_GROUP_FACTS_OPAQUE_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    group = groups[0]
    assert group.family_facts.group_id_raw == "1"
    assert group.family_facts.discount_type_raw == "9"
    assert group.family_facts.min_purchase_amount_raw == "150.00"
    assert isinstance(group.family_facts.group_id_raw, str)
    assert isinstance(group.family_facts.discount_type_raw, str)
    assert isinstance(group.family_facts.min_purchase_amount_raw, str)


# ---------------------------------------------------------------------------
# SG-T07 -- Group order preserved
# ---------------------------------------------------------------------------

_STANDARD_GROUP_ORDER_B_THEN_A_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417500",
            "description": "סדר קבוצות",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "B",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9400000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
                {
                    "group_id": "A",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9400000000002",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t07_group_output_order_matches_source_order() -> None:
    """SG-T07: Groups deliberately supplied in source order B, A must be
    emitted in that same observable order -- group_index [0, 1] tracking
    B then A, not sorted, deduplicated, or reordered by any other key.
    Only observable output order is asserted here, not implementation
    technique."""
    _promotions, groups, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_GROUP_ORDER_B_THEN_A_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert [g.family_facts.group_id_raw for g in groups] == ["B", "A"]
    assert [g.group_index for g in groups] == [0, 1]


# ---------------------------------------------------------------------------
# SG-T08 -- membership order preserved
# ---------------------------------------------------------------------------

_STANDARD_MEMBERSHIP_ORDER_C_A_B_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001417600",
            "description": "סדר פריטים",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "min_no_of_item_offered": "0",
            "groups": [
                {
                    "group_id": "1",
                    "discount_type": "0",
                    "min_purchase_amount": "0.00",
                    "items": [
                        {
                            "item_code": "9500000000003",  # C
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "9500000000001",  # A
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                        {
                            "item_code": "9500000000002",  # B
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        },
                    ],
                },
            ],
        }
    ],
)


def test_sg_t08_membership_output_order_matches_source_item_order() -> None:
    """SG-T08: items deliberately supplied in source order C, A, B within
    one Group must be emitted as memberships in that same observable order
    -- not sorted or reordered by ItemCode. No item_index is introduced
    (see T-G/SG-T01's closed field-set pin); all three memberships share
    the same group_index."""
    _promotions, groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MEMBERSHIP_ORDER_C_A_B_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert [m.retailer_item_id_raw for m in memberships] == [
        "9500000000003",  # C
        "9500000000001",  # A
        "9500000000002",  # B
    ]
    assert {m.group_index for m in memberships} == {groups[0].group_index}


# ---------------------------------------------------------------------------
# SG-T10 -- item-level economics regression
# ---------------------------------------------------------------------------


def test_sg_t10_group_preservation_does_not_move_item_level_economics() -> None:
    """SG-T10: introducing Group preservation must not move or alter
    reward_type_raw, min_qty_raw, max_qty_raw, discount_rate_raw, or
    discounted_price_raw -- they remain on StandardMembershipFacts exactly
    as raw input, unaffected by the surrounding Group structure. Reuses
    SG-T02's fixture rather than inventing a redundant one."""
    _promotions, _groups, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_ONE_GROUP_TWO_ITEMS_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    member = next(m for m in memberships if m.retailer_item_id_raw == "7290020000001")
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.reward_type_raw == "10"
    assert member.family_facts.min_qty_raw == "2"
    assert member.family_facts.max_qty_raw == "0"
    assert member.family_facts.discount_rate_raw == ""
    assert member.family_facts.discounted_price_raw == "10.00"


# ---------------------------------------------------------------------------
# SG-T11 -- Online unchanged
# ---------------------------------------------------------------------------


def test_sg_t11_online_normalization_stays_a_two_tuple_with_null_group_index() -> None:
    """SG-T11: Online normalization is unaffected by Standard's Group
    preservation -- it remains a plain 2-tuple (promotions, memberships),
    with no Group collection introduced, and every OnlineMembershipFacts
    membership now carries group_index=None (Online never had Groups to
    begin with). OnlinePromotionFacts/OnlineMembershipFacts' field sets
    and existing economics expectations (T-F) are otherwise unchanged."""
    promotions, memberships = normalize_online_promotions_occurrence(
        _ONLINE_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 1
    assert len(memberships) == 1
    member = memberships[0]
    assert member.group_index is None

    promo = promotions[0]
    assert isinstance(promo.family_facts, OnlinePromotionFacts)
    assert promo.family_facts.reward_type_raw == "1"
    assert promo.family_facts.discounted_price_raw == "19.90"


# ===========================================================================
# PHASE 2 -- failure semantics
# ===========================================================================


# ---------------------------------------------------------------------------
# T-Q -- malformed / unparseable artifact
# ---------------------------------------------------------------------------


def test_malformed_raw_artifact_fails_the_whole_occurrence_call() -> None:
    """T-Q: a structurally unacceptable raw artifact -- None, not even an
    occurrence-shaped object at all -- must fail the whole normalization
    call, with no normalized promotion or membership batch ever produced.
    Uses the smallest obviously invalid input rather than freezing a
    detailed parser schema for "malformed". Unaffected by the return-arity
    change: the ValueError fires before any return value would ever be
    constructed."""
    with pytest.raises(ValueError):
        normalize_standard_promotions_occurrence(None, collected_at=_COLLECTED_AT)


# ---------------------------------------------------------------------------
# T-R -- missing required occurrence identity/scope
# ---------------------------------------------------------------------------

_STANDARD_MISSING_STORE_ID_OCCURRENCE = _standard_occurrence(
    store_id=_OMIT,
    promotions=[
        {
            "promotion_id": "4600000",
            "description": "מבצע תקין",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "0",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290000000001",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        }
    ],
)


def test_missing_required_occurrence_store_id_fails_the_whole_occurrence_call() -> None:
    """T-R: the occurrence-level store_id_raw source fact is genuinely
    absent (not merely an empty string) -- an otherwise fully valid
    promotion and membership cannot rescue it. The whole call must fail.
    Deliberately NOT expressed as a successful NormalizedPromotion carrying
    store_id_raw=None: the approved contract's store_id_raw: str is
    non-nullable, so that state can only ever be a call failure, never a
    successful return value. Unaffected by the return-arity change."""
    with pytest.raises(ValueError):
        normalize_standard_promotions_occurrence(
            _STANDARD_MISSING_STORE_ID_OCCURRENCE, collected_at=_COLLECTED_AT
        )


# ---------------------------------------------------------------------------
# T-S -- one malformed promotion among valid promotions
# ---------------------------------------------------------------------------

_STANDARD_ONE_VALID_ONE_MALFORMED_PROMOTION_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "4600001",
            "description": "מבצע תקין",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "0",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290000000002",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        },
        {
            # Malformed: PromotionID genuinely absent.
            "promotion_id": _OMIT,
            "description": "מבצע פגום",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "0",
            "min_no_of_item_offered": "1",
            "groups": [
                {
                    "items": [
                        {
                            "item_code": "7290000000003",
                            "reward_type": "3",
                            "discount_rate": "10",
                            "discounted_price": "9.00",
                            "min_qty": "1",
                            "max_qty": "0",
                        }
                    ],
                }
            ],
        },
    ],
)


def test_one_malformed_promotion_among_valid_promotions_fails_the_whole_occurrence() -> None:
    """T-S: one occurrence containing a fully valid promotion PLUS a
    malformed one (PromotionID genuinely absent) -- the direct regression
    test for "499 valid + 1 malformed => zero accepted output", scaled
    down to 1+1. The whole call must fail; the otherwise-valid promotion
    must never be returned as a partial success. Unaffected by the
    return-arity change."""
    with pytest.raises(ValueError):
        normalize_standard_promotions_occurrence(
            _STANDARD_ONE_VALID_ONE_MALFORMED_PROMOTION_OCCURRENCE, collected_at=_COLLECTED_AT
        )


# ---------------------------------------------------------------------------
# T-T -- one malformed membership among valid memberships
# ---------------------------------------------------------------------------

_ONLINE_ONE_VALID_ONE_MALFORMED_MEMBERSHIP_OCCURRENCE = _online_occurrence(
    promotions=[
        {
            "promotion_id": "910400001",
            "description": "מבצע עם שני פריטים",
            "start_at": "2026-08-01T00:00:00",
            "end_at": "2026-08-31T23:59:00",
            "reward_type": "1",
            "discount_type": "1",
            "discount_rate": "0",
            "discounted_price": "10.00",
            "discounted_price_per_mida": "10.00",
            "min_qty": "1",
            "min_no_of_item_offered": "0",
            "max_qty": "0",
            "items": [
                {
                    "item_code": "3046920000001",
                    "is_gift_item": "0",
                    "item_type": "1",
                },
                {
                    # Malformed: ItemCode genuinely absent.
                    "item_code": _OMIT,
                    "is_gift_item": "0",
                    "item_type": "1",
                },
            ],
        }
    ],
)


def test_one_malformed_membership_among_valid_memberships_fails_the_whole_occurrence() -> None:
    """T-T: one valid promotion structure containing a fully valid
    membership PLUS a malformed one (ItemCode genuinely absent). The whole
    call must fail; neither the valid membership nor its parent promotion
    may escape as a successful partial result."""
    with pytest.raises(ValueError):
        normalize_online_promotions_occurrence(
            _ONLINE_ONE_VALID_ONE_MALFORMED_MEMBERSHIP_OCCURRENCE, collected_at=_COLLECTED_AT
        )


# ---------------------------------------------------------------------------
# T-U -- assessed, NOT written: observationally redundant at the current
# public API boundary.
#
# The public boundary is exactly: normalize_*_promotions_occurrence(raw,
# *, collected_at) either returns the complete
# tuple[list[NormalizedPromotion], list[NormalizedPromotionMembership]] (or,
# for Standard, the frozen 3-tuple once implemented) or raises. There is no
# other externally observable channel (no output parameter, no
# streaming/partial-yield API, no exposed intermediate state) through which
# a "partial result" could even be inspected -- a raise prevents any tuple
# from ever being constructed or unpacked, for ANY co-occurring
# valid+malformed combination, not just the promotion-level (T-S) and
# membership-level (T-T) cases already covered. Any further "malformed X
# alongside valid Y" fixture would produce a test structurally identical to
# T-S/T-T (call + pytest.raises(ValueError)), proving nothing beyond what
# they already establish. Writing it anyway would be inventing a new
# requirement merely to preserve the test count, which was explicitly out
# of scope for this task -- so T-U is reported as redundant instead of
# written. This reasoning is unaffected by Group preservation: no new
# externally observable partial-result channel was introduced.
# ---------------------------------------------------------------------------
