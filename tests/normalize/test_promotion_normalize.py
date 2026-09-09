"""Phase 1 RED tests for the approved Promotions Stage-1 normalization
contract (`smartcart.normalize.promotion_contract`) and its two
occurrence-level entry points (`smartcart.normalize.promotion`).

Unlike the PriceFull FIRST RED tests (test_shufersal_normalize.py,
test_rami_levy_normalize.py), which were RED because `normalize_item` did
not exist at all, `normalize_standard_promotions_occurrence` and
`normalize_online_promotions_occurrence` already exist as an approved
skeleton that unconditionally raises `NotImplementedError` -- no parsing,
mapping, or validation happens yet. Every behavioral test below therefore
calls the real public entry point directly, uncaught: the call itself
raises `NotImplementedError` before any assertion below it can run. Those
assertions are deliberately left in place (not commented out, not wrapped
in `pytest.raises`) because they encode the frozen, evidence-backed mapping
this contract commits to -- exactly as the PriceFull FIRST RED tests fixed
their mapping ahead of implementation. Once a real parser/normalizer lands,
`NotImplementedError` stops firing and these assertions become live,
without needing to be rewritten.

`raw` is test-local, ad hoc nested dicts only -- never a new production
dataclass. The skeleton's public signature accepts `raw: object`
specifically because no Promotions raw parser contract has been designed
yet (that is out of scope here, same as it was for the skeleton itself);
inventing one now, even test-only, would freeze an unjustified production
parser API. `_standard_occurrence`/`_online_occurrence` below are the sole,
centralized construction point for that synthetic nesting -- TEST
SCAFFOLDING ONLY. Their internal dict shape reads naturally against the
frozen contract's own field names but is not meaningful to the skeleton
today (it is unconditionally ignored by the `raise`), does not attempt to
mirror the Standard family's observed Groups -> Group -> PromotionItems XML
nesting, and must never be read as the future real parser/XML DTO -- that
remains a separate, not-yet-made design decision.

T-G is the one exception: it inspects the already-real dataclasses in
`promotion_contract.py` directly (no call to either entry point), so it
runs today's actual code path and is expected to be GREEN, not RED -- see
its docstring for why that is meaningful rather than vacuous.

T-Q..T-T (Phase 2, failure semantics) additionally wrap their call in
`pytest.raises(ValueError)` rather than leaving it uncaught. `ValueError`
is not a newly invented class: it is the exact convention `_require()`
already establishes in `normalize/rami_levy.py` and `normalize/shufersal.py`
for a required-field normalization-contract violation. `NotImplementedError`
does not subclass `ValueError`, so right now `pytest.raises(ValueError)`
does NOT catch the skeleton's `NotImplementedError` -- it still propagates
uncaught and fails the test, for the identical attributable reason as every
other behavioral test in this file. Once real failure semantics replace the
stub, these tests become live without rewriting.
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
dict -- distinct from a present key whose value is "". Needed only for
Phase 2's "required field is genuinely missing" fixtures (T-R/S/T); no
Phase 1 fixture uses it, and its introduction changes no Phase 1 fixture's
built dict. TEST-ONLY, never a production parser DTO concept.
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
    start_at, end_at, is_gift_item) plus an "items" list of plain per-item
    dicts (item_code, reward_type, discount_rate, discounted_price,
    min_qty, min_no_of_item_offered, max_qty). Any key a caller omits
    falls back to an inert empty-string default, so a call site only needs
    to state the field(s) relevant to what it's testing. Passing `_OMIT`
    (for chain_id/store_id, or as any promotion-/item-level field's value)
    removes that key from the built dict entirely instead of defaulting
    it, for fixtures that need genuine absence rather than "". Deliberately
    does not attempt to mirror the observed Groups -> Group ->
    PromotionItems XML nesting -- that remains a separate future design
    decision.
    """
    promotion_defaults = {
        "promotion_id": "",
        "description": "",
        "start_at": "",
        "end_at": "",
        "is_gift_item": "",
    }
    item_defaults = {
        "item_code": "",
        "reward_type": "",
        "discount_rate": "",
        "discounted_price": "",
        "min_qty": "",
        "min_no_of_item_offered": "",
        "max_qty": "",
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
    it.
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
            "items": [
                {
                    "item_code": "7290121290494",
                    "reward_type": "3",
                    "discount_rate": "33",
                    "discounted_price": "10.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                }
            ],
        }
    ],
)


def test_standard_happy_path_maps_minimal_occurrence_to_frozen_contract() -> None:
    """T-A: one promotion, one membership, every frozen shared + Standard
    family field populated -- eventual success, exact raw mapping."""
    promotions, memberships = normalize_standard_promotions_occurrence(
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
    assert member.family_facts.min_no_of_item_offered_raw == "1"
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
    OnlinePromotionFacts and OnlineMembershipFacts field."""
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
            "items": [
                {
                    "item_code": "7290016319187",
                    "reward_type": "3",
                    "discount_rate": "25",
                    "discounted_price": "14.90",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                },
                {
                    "item_code": "7290016319194",
                    "reward_type": "3",
                    "discount_rate": "25",
                    "discounted_price": "14.90",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                },
                {
                    "item_code": "7290016319200",
                    "reward_type": "3",
                    "discount_rate": "25",
                    "discounted_price": "14.90",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                },
            ],
        }
    ],
)


def test_one_promotion_with_three_skus_yields_one_promotion_and_three_memberships() -> None:
    """T-C: one occurrence, one promotion, three distinct participating
    SKUs -- one NormalizedPromotion, three NormalizedPromotionMembership,
    all linked to the same promotion_id_raw."""
    promotions, memberships = normalize_standard_promotions_occurrence(
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
            "items": [
                {
                    "item_code": "7290014066373",
                    "reward_type": "1",
                    "discount_rate": "100",
                    "discounted_price": "0.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                }
            ],
        },
        {
            "promotion_id": "0001421247",
            "description": "מבצע נוסף",
            "start_at": "2026-09-01",
            "end_at": "2026-09-30",
            "is_gift_item": "",
            "items": [
                {
                    "item_code": "7290014066373",
                    "reward_type": "3",
                    "discount_rate": "15",
                    "discounted_price": "12.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                }
            ],
        },
    ],
)


def test_same_sku_across_two_promotions_yields_two_distinct_memberships() -> None:
    """T-D: one occurrence, two promotions, the same retailer_item_id_raw
    appears under both -- two distinct memberships, same SKU identity,
    different promotion IDs, no accidental dedup/merge."""
    promotions, memberships = normalize_standard_promotions_occurrence(
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
    """T-E: Standard economic fields (RewardType, DiscountRate,
    DiscountedPrice, MinQty, MinNoOfItemOffered, MaxQty) must normalize
    into StandardMembershipFacts -- never onto StandardPromotionFacts or
    the shared NormalizedPromotion envelope."""
    promotions, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_MINIMAL_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    promo = promotions[0]
    assert isinstance(promo.family_facts, StandardPromotionFacts)
    # StandardPromotionFacts' only declared field is is_gift_item_raw --
    # this is a positive assertion on the actual value landing there, not
    # a shape re-check (that's T-G's job).
    assert promo.family_facts.is_gift_item_raw == "0"

    member = memberships[0]
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.reward_type_raw == "3"
    assert member.family_facts.discount_rate_raw == "33"
    assert member.family_facts.discounted_price_raw == "10.00"
    assert member.family_facts.min_qty_raw == "1"
    assert member.family_facts.min_no_of_item_offered_raw == "1"
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
# T-G -- exact positive contract shape / family isolation
# ---------------------------------------------------------------------------


def test_frozen_contract_shape_is_a_closed_positive_enumeration() -> None:
    """T-G: assert the frozen contract's exact field sets directly against
    the real dataclasses -- a closed positive enumeration, not a blacklist
    of forbidden field names. Absorbs the former T-V intent.

    This test does not call either normalize entry point, so it is NOT
    subject to the skeleton's NotImplementedError -- it exercises real,
    already-existing production code (the dataclass definitions
    themselves) and is expected to be GREEN today. It remains meaningful
    (not vacuous) because it pins the exact field set now, so any future
    accidental field addition/removal/rename on these six types -- in
    either direction -- fails this test immediately, before any behavioral
    implementation exists to hide the drift.
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
    }
    assert {f.name for f in dataclasses.fields(StandardPromotionFacts)} == {
        "is_gift_item_raw",
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
        "min_no_of_item_offered_raw",
        "max_qty_raw",
    }
    assert {f.name for f in dataclasses.fields(OnlineMembershipFacts)} == {
        "is_gift_item_raw",
        "item_type_raw",
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
            "items": [
                {
                    "item_code": "8006530264495",
                    "reward_type": "2",
                    "discount_rate": "100",
                    "discounted_price": "0.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                }
            ],
        }
    ],
)


def test_standard_non_boolean_is_gift_item_is_preserved_raw_without_bool_coercion() -> None:
    """T-H: a non-boolean IsGiftItem source value ("1.5") must survive
    exactly as a string on StandardPromotionFacts -- never coerced to
    True/False, never rejected as invalid."""
    promotions, _memberships = normalize_standard_promotions_occurrence(
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
# T-J -- MinQty and MinNoOfItemOffered stay independent
# ---------------------------------------------------------------------------

_STANDARD_DIVERGENT_QTY_FIELDS_OCCURRENCE = _standard_occurrence(
    promotions=[
        {
            "promotion_id": "0001379851",
            "description": "מאגדת שלגונים",
            "start_at": "2026-08-01",
            "end_at": "2026-08-31",
            "is_gift_item": "",
            "items": [
                {
                    "item_code": "7290002680178",
                    "reward_type": "3",
                    "discount_rate": "34.75",
                    "discounted_price": "16.90",
                    # Real observed divergence from prior recon: MinQty=1
                    # while MinNoOfItemOffered=10 on the same record.
                    "min_qty": "1",
                    "min_no_of_item_offered": "10",
                    "max_qty": "0",
                }
            ],
        }
    ],
)


def test_min_qty_and_min_no_of_item_offered_survive_independently() -> None:
    """T-J: distinct source values for MinQty and MinNoOfItemOffered must
    both survive independently on StandardMembershipFacts -- never
    merged/collapsed into one, even though they sound related."""
    _promotions, memberships = normalize_standard_promotions_occurrence(
        _STANDARD_DIVERGENT_QTY_FIELDS_OCCURRENCE, collected_at=_COLLECTED_AT
    )

    member = memberships[0]
    assert isinstance(member.family_facts, StandardMembershipFacts)
    assert member.family_facts.min_qty_raw == "1"
    assert member.family_facts.min_no_of_item_offered_raw == "10"
    assert member.family_facts.min_qty_raw != member.family_facts.min_no_of_item_offered_raw


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
            "items": [
                {
                    "item_code": "7290099999999",
                    # Unrecognized/never-before-observed RewardType value.
                    "reward_type": "99",
                    "discount_rate": "10",
                    "discounted_price": "9.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
                }
            ],
        }
    ],
)


def test_unknown_reward_type_normalizes_as_valid_opaque_data() -> None:
    """T-L: an unrecognized RewardType value ("99") must normalize
    successfully and round-trip unchanged -- unknown semantic meaning must
    NOT itself be modeled as malformed/rejected data."""
    _promotions, memberships = normalize_standard_promotions_occurrence(
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
    promotions, memberships = normalize_standard_promotions_occurrence(
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
    promotions, _memberships = normalize_standard_promotions_occurrence(
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
    promotions, _memberships = normalize_standard_promotions_occurrence(
        _STANDARD_SAME_SKU_TWO_PROMOTIONS, collected_at=_COLLECTED_AT
    )

    assert len(promotions) == 2
    for promo in promotions:
        assert promo.retailer_chain_id == _STANDARD_CHAIN_ID
        assert promo.store_id_raw == _STANDARD_STORE_ID
        assert promo.source_family == "standard"


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
    detailed parser schema for "malformed"."""
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
            "items": [
                {
                    "item_code": "7290000000001",
                    "reward_type": "3",
                    "discount_rate": "10",
                    "discounted_price": "9.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
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
    successful return value."""
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
            "items": [
                {
                    "item_code": "7290000000002",
                    "reward_type": "3",
                    "discount_rate": "10",
                    "discounted_price": "9.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
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
            "items": [
                {
                    "item_code": "7290000000003",
                    "reward_type": "3",
                    "discount_rate": "10",
                    "discounted_price": "9.00",
                    "min_qty": "1",
                    "min_no_of_item_offered": "1",
                    "max_qty": "0",
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
    must never be returned as a partial success."""
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
# tuple[list[NormalizedPromotion], list[NormalizedPromotionMembership]] or
# raises. There is no other externally observable channel (no output
# parameter, no streaming/partial-yield API, no exposed intermediate
# state) through which a "partial result" could even be inspected -- a
# raise prevents any tuple from ever being constructed or unpacked, for
# ANY co-occurring valid+malformed combination, not just the promotion-
# level (T-S) and membership-level (T-T) cases already covered. Any
# further "malformed X alongside valid Y" fixture would produce a test
# structurally identical to T-S/T-T (call + pytest.raises(ValueError)),
# proving nothing beyond what they already establish. Writing it anyway
# would be inventing a new requirement merely to preserve the test count,
# which was explicitly out of scope for this task -- so T-U is reported
# as redundant instead of written.
# ---------------------------------------------------------------------------
