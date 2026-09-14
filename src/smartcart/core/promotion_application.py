"""Slice-1 promotion-application seam (see
tests/core/test_promotion_application.py).

Pure data-shape declarations for `FixedBundleRule`/`FixedBundleEvaluation`
only -- no validation, no methods beyond what @dataclass generates by
default -- mirrors the role `promotion_contract.py` plays for the
Promotions normalization contract. `evaluate_fixed_bundle` applies at most
one fixed-bundle grouping (never repeated, even if basket_qty could satisfy
it more than once) and returns an explicit, always-populated
`FixedBundleEvaluation` whether or not the bundle's trigger quantity is met.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class FixedBundleRule:
    required_qty: int
    bundle_total: Decimal


@dataclass(frozen=True)
class FixedBundleEvaluation:
    consumed_qty: int
    consumed_ordinary_cost: Decimal
    promotional_cost: Decimal
    unmatched_qty: int
    unmatched_ordinary_cost: Decimal
    total_cost: Decimal
    savings: Decimal


def evaluate_fixed_bundle(
    rule: FixedBundleRule,
    basket_qty: int,
    ordinary_unit_price: Decimal,
) -> FixedBundleEvaluation:
    if basket_qty >= rule.required_qty:
        consumed_qty = rule.required_qty
        promotional_cost = rule.bundle_total
    else:
        consumed_qty = 0
        promotional_cost = Decimal("0")

    consumed_ordinary_cost = consumed_qty * ordinary_unit_price
    unmatched_qty = basket_qty - consumed_qty
    unmatched_ordinary_cost = unmatched_qty * ordinary_unit_price
    total_cost = promotional_cost + unmatched_ordinary_cost
    savings = consumed_ordinary_cost - promotional_cost

    return FixedBundleEvaluation(
        consumed_qty=consumed_qty,
        consumed_ordinary_cost=consumed_ordinary_cost,
        promotional_cost=promotional_cost,
        unmatched_qty=unmatched_qty,
        unmatched_ordinary_cost=unmatched_ordinary_cost,
        total_cost=total_cost,
        savings=savings,
    )
