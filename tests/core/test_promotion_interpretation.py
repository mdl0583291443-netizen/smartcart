"""Slice-2 tests for the approved `smartcart.core.promotion_interpretation`
seam: interpreting the ECONOMICS ONLY (required quantity, bundle total) of an
already-classified fixed-bundle promotion from Stage-1 normalized facts into a
Slice-1 `FixedBundleRule`.

Every fixture below is constructed directly as a real Stage-1
`StandardMembershipFacts`/`OnlinePromotionFacts` instance (never via
`normalize_standard_promotions_occurrence`/`normalize_online_promotions_occurrence`
or a raw retailer dict/XML builder). Each input is already treated as a known
fixed-bundle case: recognition/classification of a promotion as fixed-bundle,
SKU scope, multi-SKU aggregation, and basket application are all out of scope
for this slice and are not exercised by any test here.

A behavioral RED (every assertion below failing for the intentional reason a
logic-free skeleton's stub produces, not for an unrelated import/collection
failure) is verified only once a logic-free `promotion_interpretation.py`
skeleton exists -- a separate, later step, matching how Slice 1 proceeded.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from smartcart.core.promotion_interpretation import (
    interpret_rami_online_fixed_bundle_economics,
    interpret_rami_standard_fixed_bundle_economics,
)
from smartcart.normalize.promotion_contract import (
    OnlinePromotionFacts,
    StandardMembershipFacts,
)


def test_pe_i02_rami_standard_real_evidence_interprets_required_qty_and_bundle_total() -> None:
    """PE-I02: real Rami Levy Standard evidence -- store 001, PromotionID
    0001417009, description "חטיפי אסם עד 80גרם 10ב30" (a real 8-SKU
    promotion; only one representative membership's economics are used
    here, since multi-SKU aggregation is out of scope for this slice).
    Load-bearing real values: MinQty="10", DiscountedPrice="30.00"."""
    facts = StandardMembershipFacts(
        # Non-load-bearing: this slice makes no real-evidence claim about
        # these fields, so None (not an invented placeholder string).
        reward_type_raw=None,
        discount_rate_raw=None,
        # Real evidence (Rami Levy Standard, store 001, PromotionID
        # 0001417009, "חטיפי אסם עד 80גרם 10ב30").
        discounted_price_raw="30.00",
        min_qty_raw="10",
        # Non-load-bearing -- see reward_type_raw/discount_rate_raw above.
        max_qty_raw=None,
    )

    result = interpret_rami_standard_fixed_bundle_economics(facts)

    assert result.required_qty == 10
    assert result.bundle_total == Decimal("30.00")


def test_pe_i03_rami_online_real_evidence_does_not_use_discounted_price_per_mida() -> None:
    """PE-I03: real Rami Levy Online evidence -- store 039, PromotionID
    910370791, description "נוזל כביסה כביסכל 2 יח' ב-90 ש\"ח" (a real
    8-SKU promotion; only one representative promotion-level economics
    fact is used here, since multi-SKU aggregation is out of scope for
    this slice). Load-bearing real values: MinQty="2", DiscountedPrice="90",
    DiscountedPricePerMida="45" -- the last one is included specifically to
    prove it must NOT be mistaken for the bundle total."""
    facts = OnlinePromotionFacts(
        # Non-load-bearing: this slice makes no real-evidence claim about
        # these fields, so None (not an invented placeholder string).
        reward_type_raw=None,
        discount_type_raw=None,
        discount_rate_raw=None,
        # Real evidence (Rami Levy Online, store 039, PromotionID
        # 910370791, "נוזל כביסה כביסכל 2 יח' ב-90 ש\"ח").
        discounted_price_raw="90",
        discounted_price_per_mida_raw="45",
        min_qty_raw="2",
        # Non-load-bearing -- see reward_type_raw/discount_type_raw above.
        min_no_of_item_offered_raw=None,
        max_qty_raw=None,
    )

    result = interpret_rami_online_fixed_bundle_economics(facts)

    assert result.required_qty == 2
    assert result.bundle_total == Decimal("90")


def test_pe_i10_rami_standard_missing_min_qty_raises_value_error() -> None:
    """PE-I10: a deliberate contract mutation of the Standard real-evidence
    fixture above (`min_qty_raw` set to None does not represent an observed
    retailer value) -- a fixed-bundle case with a missing required economic
    field must not produce a guessed FixedBundleRule; interpretation must
    fail loudly instead. Recognition is not under test."""
    facts = StandardMembershipFacts(
        reward_type_raw=None,
        discount_rate_raw=None,
        discounted_price_raw="30.00",
        min_qty_raw=None,
        max_qty_raw=None,
    )

    with pytest.raises(ValueError):
        interpret_rami_standard_fixed_bundle_economics(facts)


def test_pe_i10_rami_online_unparseable_min_qty_raises_value_error() -> None:
    """PE-I10: a deliberate contract mutation of the Online real-evidence
    fixture above (`min_qty_raw="not-a-number"` does not represent an
    observed retailer value) -- a fixed-bundle case with an unparseable
    required economic field must not produce a guessed FixedBundleRule;
    interpretation must fail loudly instead."""
    facts = OnlinePromotionFacts(
        reward_type_raw=None,
        discount_type_raw=None,
        discount_rate_raw=None,
        discounted_price_raw="90",
        discounted_price_per_mida_raw=None,
        min_qty_raw="not-a-number",
        min_no_of_item_offered_raw=None,
        max_qty_raw=None,
    )

    with pytest.raises(ValueError):
        interpret_rami_online_fixed_bundle_economics(facts)


def test_pe_i10_rami_online_missing_discounted_price_raises_value_error() -> None:
    """PE-I10: a deliberate contract mutation of the Online real-evidence
    fixture above (`discounted_price_raw=None` does not represent an
    observed retailer value) -- DiscountedPricePerMida="45" being present
    must NOT let the interpreter substitute it as bundle_total when
    DiscountedPrice itself is missing; interpretation must fail loudly
    instead."""
    facts = OnlinePromotionFacts(
        reward_type_raw=None,
        discount_type_raw=None,
        discount_rate_raw=None,
        discounted_price_raw=None,
        discounted_price_per_mida_raw="45",
        min_qty_raw="2",
        min_no_of_item_offered_raw=None,
        max_qty_raw=None,
    )

    with pytest.raises(ValueError):
        interpret_rami_online_fixed_bundle_economics(facts)


def test_pe_i10_rami_standard_unparseable_discounted_price_raises_value_error() -> None:
    """PE-I10: a deliberate contract mutation of the Standard real-evidence
    fixture above (`discounted_price_raw="not-a-number"` does not represent
    an observed retailer value) -- a fixed-bundle case with an unparseable
    required economic field must not produce a guessed FixedBundleRule;
    interpretation must fail loudly instead."""
    facts = StandardMembershipFacts(
        reward_type_raw=None,
        discount_rate_raw=None,
        discounted_price_raw="not-a-number",
        min_qty_raw="10",
        max_qty_raw=None,
    )

    with pytest.raises(ValueError):
        interpret_rami_standard_fixed_bundle_economics(facts)


def test_pe_i10_fixed_bundle_quantity_is_not_silently_truncated() -> None:
    """PE-I10: a deliberate contract mutation (`min_qty_raw="10.50"` does
    not represent an observed retailer value) proving int(...)-truncation
    contract enforcement, not a weighted-quantity semantic claim -- this
    slice's output contract is `FixedBundleRule.required_qty: int`, so a
    parseable-but-non-integral quantity must raise ValueError rather than
    being silently truncated to 10. This does NOT establish that fractional
    MinQty is globally invalid: weighted/fractional-quantity semantics
    remain outside this slice and may be valid in a future weighted-products
    path."""
    facts = StandardMembershipFacts(
        reward_type_raw=None,
        discount_rate_raw=None,
        discounted_price_raw="30.00",
        min_qty_raw="10.50",
        max_qty_raw=None,
    )

    with pytest.raises(ValueError):
        interpret_rami_standard_fixed_bundle_economics(facts)
