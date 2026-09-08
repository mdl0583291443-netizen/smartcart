"""FIRST RED tests for the not-yet-implemented common price-item
normalization contract, exercised against Shufersal PriceFull raw records.

This is deliberately RED: `smartcart.normalize.contract.NormalizedPriceItem`
and `smartcart.normalize.shufersal.normalize_item` do not exist yet. These
tests fix the frozen normalized contract's shape and mapping semantics
ahead of that implementation (see docs/adr/0004 step 5 -- "normalize the
validated data into a normalized internal representation" -- and docs/adr/
0008, which explicitly defers "normalization/matching design" to its own
decision). No normalization production code is added alongside these
tests.

Covers matrix cases 1, 2, 3, 4, 5, 6, 7. Cross-retailer case (Rami Levy)
lives in test_rami_levy_normalize.py.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from smartcart.collectors.shufersal.records import ShufersalPriceItemRaw
from smartcart.normalize.contract import NormalizedPriceItem
from smartcart.normalize.shufersal import normalize_item

_COLLECTED_AT = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)

_CONTRACT_FIELD_NAMES = {
    "retailer_chain_id",
    "retailer_item_id",
    "store_id",
    "published_price",
    "published_price_raw",
    "declared_quantity",
    "declared_quantity_raw",
    "declared_quantity_unit_raw",
    "is_weighted",
    "product_name",
    "collected_at",
}

# Real Shufersal chain GLN (7290027600007), subchain/store pair already used
# by tests/collectors/shufersal/test_parse.py and test_validate.py. Other
# item-level values are schema-shape-accurate (per this repo's established
# convention -- see test_parse.py's own module docstring) rather than a
# literal captured payload, since no such fixture file exists in this repo.
_BASE_ITEM = ShufersalPriceItemRaw(
    chain_id="7290027600007",
    subchain_id="002",
    store_id="413",
    bikoret_no="0",
    price_update_time="2026-09-04T06:23:00",
    item_code="7290004125023",
    last_sale_date_time="2026-09-04T00:00:00",
    item_type="1",
    item_name="חלב טרי 3% תנובה 1 ליטר",
    manufacture_name="תנובה",
    manufacture_country="IL",
    # Deliberately different from item_name: proves product_name is sourced
    # from ItemName, not ManufactureItemDescription (neither of which is
    # part of the common normalized contract in any case).
    manufacture_item_description="DECOY - must not appear in product_name",
    unit_qty="Liter",
    quantity="1",
    unit_of_measure="1 Liter",
    is_weighted="0",
    qty_in_package="1",
    item_price="6.90",
    unit_of_measure_price="6.90",
    allow_discount="1",
    item_status=None,
)


def test_ordinary_fixed_quantity_product_maps_directly_to_contract() -> None:
    """Case 1: prove the complete frozen normalized shape and direct
    mapping for an ordinary fixed-quantity product."""
    normalized = normalize_item(_BASE_ITEM, collected_at=_COLLECTED_AT)

    assert isinstance(normalized, NormalizedPriceItem)
    assert normalized.retailer_chain_id == "7290027600007"
    assert normalized.retailer_item_id == "7290004125023"
    assert normalized.store_id == "413"
    assert normalized.published_price == Decimal("6.90")
    assert normalized.published_price_raw == "6.90"
    assert normalized.declared_quantity == Decimal("1")
    assert normalized.declared_quantity_raw == "1"
    assert normalized.declared_quantity_unit_raw == "Liter"
    assert normalized.is_weighted is False
    # ItemName != ManufactureItemDescription on this fixture (see _BASE_ITEM)
    # -- this pins product_name to ItemName specifically.
    assert normalized.product_name == "חלב טרי 3% תנובה 1 ליטר"
    assert normalized.product_name == _BASE_ITEM.item_name
    assert normalized.collected_at == _COLLECTED_AT
    assert {f.name for f in dataclasses.fields(normalized)} == _CONTRACT_FIELD_NAMES


def test_weighted_product_flag_is_taken_directly_from_source() -> None:
    """Case 2: bIsWeighted=1 -> is_weighted=True; Quantity remains the
    published declared quantity; no attempt is made to interpret it as
    actual checkout weight."""
    weighted_item = replace(
        _BASE_ITEM,
        item_code="7290004999999",
        item_name="עגבניות שרי",
        # manufacture_item_description intentionally left at _BASE_ITEM's
        # decoy value (differs from item_name) -- see contract-source note
        # on _BASE_ITEM.
        unit_qty="Kilogram",
        quantity="1.000",
        unit_of_measure="1 Kilogram",
        is_weighted="1",
        item_price="8.90",
        unit_of_measure_price="8.90",
    )

    normalized = normalize_item(weighted_item, collected_at=_COLLECTED_AT)

    assert normalized.is_weighted is True
    assert normalized.declared_quantity == Decimal("1.000")
    assert normalized.declared_quantity_raw == "1.000"


def test_multipack_product_name_and_quantity_preserved_without_composition_inference() -> None:
    """Case 3 (Coke evidence): product_name preserved, declared quantity
    remains 1.98L, and the normalized output contains no pack-count/
    per-unit-size/composition fields. Quantity=1.98L must NOT be used to
    infer 6x330ml package composition."""
    coke = replace(
        _BASE_ITEM,
        item_code="7290004125030",
        item_name='קוקה קולה 6*330 מ"ל',
        manufacture_name="קוקה קולה ישראל",
        # manufacture_item_description intentionally left at _BASE_ITEM's
        # decoy value (differs from item_name).
        unit_qty="Liter",
        quantity="1.98",
        unit_of_measure="1.98 Liter",
        is_weighted="0",
        qty_in_package="6",
        item_price="23.90",
        unit_of_measure_price="12.07",
    )

    normalized = normalize_item(coke, collected_at=_COLLECTED_AT)

    assert normalized.product_name == 'קוקה קולה 6*330 מ"ל'
    assert normalized.declared_quantity == Decimal("1.98")
    assert normalized.declared_quantity_raw == "1.98"
    assert normalized.declared_quantity_unit_raw == "Liter"
    # ItemPrice ("23.90") != UnitOfMeasurePrice ("12.07") on this fixture:
    # proves published_price is sourced from ItemPrice and cannot
    # accidentally be fed by the excluded UnitOfMeasurePrice field.
    assert normalized.published_price == Decimal("23.90")
    assert normalized.published_price_raw == "23.90"

    field_names = {f.name for f in dataclasses.fields(normalized)}
    assert field_names == _CONTRACT_FIELD_NAMES
    for forbidden in (
        "pack_count",
        "unit_count",
        "per_unit_size",
        "per_unit_quantity",
        "composition",
        "inferred_pack_count",
    ):
        assert not hasattr(normalized, forbidden)


def test_decimal_and_raw_fidelity_for_non_trivial_formatting() -> None:
    """Case 4: published_price == Decimal(published_price_raw) and
    declared_quantity == Decimal(declared_quantity_raw) exactly, with raw
    strings -- including semantically-meaningful trailing zeros -- left
    unchanged."""
    item = replace(
        _BASE_ITEM,
        item_code="7290004125047",
        item_price="8.00",
        unit_of_measure_price="8.00",
        quantity="0.330",
        unit_qty="Liter",
        unit_of_measure="0.330 Liter",
    )

    normalized = normalize_item(item, collected_at=_COLLECTED_AT)

    assert normalized.published_price == Decimal(normalized.published_price_raw)
    assert normalized.declared_quantity == Decimal(normalized.declared_quantity_raw)
    assert normalized.published_price_raw == "8.00"
    assert normalized.declared_quantity_raw == "0.330"
    # Trailing zeros are semantically meaningful (330ml, not 33ml) and must
    # not be renormalized away by a naive float round-trip.
    assert str(normalized.published_price) == "8.00"
    assert str(normalized.declared_quantity) == "0.330"


def test_product_name_fidelity_no_trim_no_collapse_no_rewrite() -> None:
    """Case 5: a source name with punctuation, a percent sign, an escaped
    quote character, and meaningful double-spacing must survive completely
    unmodified -- no trim, whitespace collapse, correction, translation, or
    rewriting."""
    tricky_name = "גבינה צהובה עמק 28%  200 גר' - פרוסות"
    item = replace(
        _BASE_ITEM,
        item_code="7290004125054",
        item_name=tricky_name,
        # manufacture_item_description intentionally left at _BASE_ITEM's
        # decoy value (differs from item_name).
    )

    normalized = normalize_item(item, collected_at=_COLLECTED_AT)

    assert normalized.product_name == tricky_name


def test_determinism_same_input_and_collected_at_yields_identical_output() -> None:
    """Case 6: normalizing the exact same input twice, including identical
    collected_at, must produce value-identical output -- no datetime.now(),
    random IDs, or other run-specific values may leak in."""
    first = normalize_item(_BASE_ITEM, collected_at=_COLLECTED_AT)
    second = normalize_item(_BASE_ITEM, collected_at=_COLLECTED_AT)

    assert first == second


def test_excluded_fields_do_not_leak_into_normalized_output() -> None:
    """Case 7: UnitOfMeasure, UnitOfMeasurePrice, QtyInPackage, and
    AllowDiscount are all present with real values on the source item, but
    must not exist anywhere in the common normalized output."""
    item = replace(
        _BASE_ITEM,
        item_code="7290004125061",
        unit_of_measure="1 Liter",
        unit_of_measure_price="6.90",
        qty_in_package="6",
        allow_discount="0",
    )

    normalized = normalize_item(item, collected_at=_COLLECTED_AT)

    field_names = {f.name for f in dataclasses.fields(normalized)}
    assert field_names == _CONTRACT_FIELD_NAMES
    for excluded in (
        "unit_of_measure",
        "unit_of_measure_price",
        "qty_in_package",
        "allow_discount",
    ):
        assert not hasattr(normalized, excluded)
