"""Slice-2 fixed-bundle-economics interpretation seam (see
tests/core/test_promotion_interpretation.py).

Both functions interpret ECONOMICS ONLY (required quantity, bundle total) of
Stage-1 facts already classified as fixed-bundle promotions. They read only
`min_qty_raw` and `discounted_price_raw` -- no other field (RewardType,
DiscountType, DiscountRate, DiscountedPricePerMida, MinNoOfItemOffered,
MaxQty) is inspected. Recognition/classification, SKU scope, multi-SKU
aggregation, and basket application remain out of scope for this slice.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from smartcart.core.promotion_application import FixedBundleRule
from smartcart.normalize.promotion_contract import (
    OnlinePromotionFacts,
    StandardMembershipFacts,
)


def _parse_required_qty(raw: str | None) -> int:
    if raw is None:
        raise ValueError("required quantity is missing")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"required quantity {raw!r} is not a parseable number") from exc
    if value != value.to_integral_value():
        raise ValueError(f"required quantity {raw!r} is not an integral quantity")
    return int(value)


def _parse_bundle_total(raw: str | None) -> Decimal:
    if raw is None:
        raise ValueError("bundle total is missing")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"bundle total {raw!r} is not a parseable Decimal") from exc


def interpret_rami_standard_fixed_bundle_economics(
    facts: StandardMembershipFacts,
) -> FixedBundleRule:
    return FixedBundleRule(
        required_qty=_parse_required_qty(facts.min_qty_raw),
        bundle_total=_parse_bundle_total(facts.discounted_price_raw),
    )


def interpret_rami_online_fixed_bundle_economics(
    facts: OnlinePromotionFacts,
) -> FixedBundleRule:
    return FixedBundleRule(
        required_qty=_parse_required_qty(facts.min_qty_raw),
        bundle_total=_parse_bundle_total(facts.discounted_price_raw),
    )
