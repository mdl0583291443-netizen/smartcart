"""Slice-1 RED tests for the approved `smartcart.core.promotion_application`
seam: applying one already-interpreted, single-SKU fixed-bundle promotion to
one basket quantity at an ordinary unit price.

This module and its public names (`FixedBundleRule`, `FixedBundleEvaluation`,
`evaluate_fixed_bundle`) do not exist yet -- the approved seam is new, not a
transcription of existing code. Every test below is expected to fail at
collection/import time (`ModuleNotFoundError: No module named
'smartcart.core.promotion_application'`), not on an assertion, until that
module is implemented to the approved shape. Fixtures are deliberately
semantic (a `FixedBundleRule`, not retailer-shaped raw XML/dicts): this is a
Slice-1 application-primitive test, not a PE-I interpretation test, so no
`RewardType` mapping, validity/eligibility, repeatability, stacking, caps, or
multi-SKU behavior is exercised here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from smartcart.core.promotion_application import (
    FixedBundleRule,
    evaluate_fixed_bundle,
)

_RULE = FixedBundleRule(required_qty=2, bundle_total=Decimal("10"))
_ORDINARY_UNIT_PRICE = Decimal("6")


def test_pe_a01_exact_bundle_is_fully_consumed() -> None:
    """PE-A01: basket_qty exactly matches the bundle's required_qty."""
    result = evaluate_fixed_bundle(_RULE, basket_qty=2, ordinary_unit_price=_ORDINARY_UNIT_PRICE)

    assert result.consumed_qty == 2
    assert result.consumed_ordinary_cost == Decimal("12")
    assert result.promotional_cost == Decimal("10")
    assert result.unmatched_qty == 0
    assert result.unmatched_ordinary_cost == Decimal("0")
    assert result.total_cost == Decimal("10")
    assert result.savings == Decimal("2")


def test_pe_a02_bundle_plus_remainder_applies_once() -> None:
    """PE-A02: one bundle applies; the remaining unit is left unmatched at
    ordinary price. Repeated application is deliberately not inferred or
    asserted -- Slice 1 covers exactly one bundle application."""
    result = evaluate_fixed_bundle(_RULE, basket_qty=3, ordinary_unit_price=_ORDINARY_UNIT_PRICE)

    assert result.consumed_qty == 2
    assert result.consumed_ordinary_cost == Decimal("12")
    assert result.promotional_cost == Decimal("10")
    assert result.unmatched_qty == 1
    assert result.unmatched_ordinary_cost == Decimal("6")
    assert result.total_cost == Decimal("16")
    assert result.savings == Decimal("2")


def test_pe_a10_trigger_not_met_evaluation_is_explicit_and_observable() -> None:
    """PE-A10: basket_qty is below required_qty, so the bundle does not
    apply. The evaluation result must still be returned and observable --
    no `None`, `applied` boolean, or status enum is introduced or asserted
    here; non-application is expressed purely through the same observable
    fields as every other scenario (zero consumed/promotional, full
    unmatched at ordinary price)."""
    result = evaluate_fixed_bundle(_RULE, basket_qty=1, ordinary_unit_price=_ORDINARY_UNIT_PRICE)

    assert result.consumed_qty == 0
    assert result.consumed_ordinary_cost == Decimal("0")
    assert result.promotional_cost == Decimal("0")
    assert result.unmatched_qty == 1
    assert result.unmatched_ordinary_cost == Decimal("6")
    assert result.total_cost == Decimal("6")
    assert result.savings == Decimal("0")


@pytest.mark.parametrize("basket_qty", [1, 2, 3])
def test_pe_a13_consumed_and_unmatched_quantity_conserve_basket_qty(basket_qty: int) -> None:
    """PE-A13: across every approved Slice-1 scenario, consumed_qty and
    unmatched_qty must exactly account for basket_qty, and consumed_qty
    must never exceed it."""
    result = evaluate_fixed_bundle(
        _RULE, basket_qty=basket_qty, ordinary_unit_price=_ORDINARY_UNIT_PRICE
    )

    assert result.consumed_qty + result.unmatched_qty == basket_qty
    assert result.consumed_qty <= basket_qty


def test_pe_a14_unmatched_quantity_is_costed_at_ordinary_unit_price() -> None:
    """PE-A14: for a bundle-plus-remainder basket, unmatched_ordinary_cost
    must equal unmatched_qty priced at the ordinary unit price -- not a
    discounted or otherwise derived rate -- and total_cost must be exactly
    the sum of promotional_cost and unmatched_ordinary_cost."""
    result = evaluate_fixed_bundle(_RULE, basket_qty=3, ordinary_unit_price=_ORDINARY_UNIT_PRICE)

    assert result.unmatched_ordinary_cost == result.unmatched_qty * _ORDINARY_UNIT_PRICE
    assert result.total_cost == result.promotional_cost + result.unmatched_ordinary_cost
