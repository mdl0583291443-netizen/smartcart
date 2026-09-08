"""RED tests for the not-yet-implemented Rami Levy "standard" schema
family normalizer (see docs/adr/0007 for the standard/online family
split; tests/normalize/test_rami_levy_normalize.py covers the online
family, already implemented).

`smartcart.normalize.rami_levy.normalize_standard_item` does not exist
yet. These tests fix the approved Standard -> NormalizedPriceItem mapping
ahead of that implementation:

    retailer_chain_id <- ChainID
    retailer_item_id <- ItemCode
    store_id <- StoreID
    published_price_raw <- ItemPrice; published_price <- Decimal(ItemPrice)
    declared_quantity_raw <- Quantity; declared_quantity <- Decimal(Quantity)
    declared_quantity_unit_raw <- UnitQty
    is_weighted <- bIsWeighted ("1" -> True, "0" -> False, None -> None)
    product_name <- ItemName
    collected_at <- caller-supplied, unchanged

No production normalization code is added alongside these tests.
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from smartcart.collectors.rami_levy.records import RamiLevyPriceItemRawStandard
from smartcart.normalize.contract import NormalizedPriceItem
from smartcart.normalize.rami_levy import normalize_standard_item

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

# Real Rami Levy chain GLN (7290058140886) and the standard-family
# store/item identity shape, matching the base fixture already used by
# tests/collectors/rami_levy/test_validate.py's _BASE_STANDARD_ITEM.
_BASE_ITEM = RamiLevyPriceItemRawStandard(
    chain_id="7290058140886",
    subchain_id="001",
    store_id="731",
    bikoret_no="0",
    price_update_time="2026-04-27T11:19:43.000",
    item_code="7290000139159",
    last_sale_date_time="2026-08-19T16:40:12.000",
    item_type="1",
    item_name="Test Item",
    manufacture_name="לא ידוע",
    manufacture_country="לא ידוע",
    # Deliberately different from item_name (see
    # tests/collectors/rami_levy/test_parse.py's own reconnaissance-shaped
    # fixture, which likewise uses distinct ItemName/ManufactureItemDescription
    # values): proves product_name is sourced from ItemName, not
    # ManufactureItemDescription (neither of which is part of the common
    # normalized contract in any case).
    manufacture_item_description="DECOY - must not appear in product_name",
    unit_qty="גרם",
    quantity="100.00",
    unit_of_measure="100 גרם",
    is_weighted="0",
    qty_in_package="לא ידוע",
    item_price="10.20",
    unit_of_measure_price="3.68",
    allow_discount="1",
    item_status=None,
)


def test_ordinary_standard_record_maps_directly_to_contract() -> None:
    """Complete frozen shape + direct mapping for an ordinary Standard
    record, using the repo's own established Standard base fixture (see
    tests/collectors/rami_levy/test_validate.py's _BASE_STANDARD_ITEM)."""
    normalized = normalize_standard_item(_BASE_ITEM, collected_at=_COLLECTED_AT)

    assert isinstance(normalized, NormalizedPriceItem)
    assert normalized.retailer_chain_id == "7290058140886"
    assert normalized.retailer_item_id == "7290000139159"
    assert normalized.store_id == "731"
    assert normalized.published_price == Decimal("10.20")
    assert normalized.published_price_raw == "10.20"
    assert normalized.declared_quantity == Decimal("100.00")
    assert normalized.declared_quantity_raw == "100.00"
    assert normalized.declared_quantity_unit_raw == "גרם"
    assert normalized.is_weighted is False
    # ItemName != ManufactureItemDescription on this fixture -- pins
    # product_name to ItemName specifically.
    assert normalized.product_name == "Test Item"
    assert normalized.product_name == _BASE_ITEM.item_name
    assert normalized.collected_at == _COLLECTED_AT
    assert {f.name for f in dataclasses.fields(normalized)} == _CONTRACT_FIELD_NAMES


def test_weighted_standard_record_flag_is_taken_directly_from_source() -> None:
    """bIsWeighted=1 -> is_weighted=True, direct pass-through.

    EVIDENCE NOTE: no checked-in Standard-family fixture has been directly
    observed with bIsWeighted="1" -- only "0" appears in this repo's
    existing Standard evidence. This test's "1" value is an evidence-based
    inference from docs/adr/0007, which documents the standard family as
    using "the same 17-tag Item schema observed for Shufersal" (including
    bIsWeighted) -- a schema element already directly evidenced with "1"
    for Shufersal. It is not itself directly observed Standard evidence.
    """
    weighted_item = replace(_BASE_ITEM, is_weighted="1")

    normalized = normalize_standard_item(weighted_item, collected_at=_COLLECTED_AT)

    assert normalized.is_weighted is True


def test_required_field_none_raises_contract_guard_error() -> None:
    """A required nullable raw field (ItemPrice, here) being None must
    raise ValueError from the normalizer's minimal contract guard -- the
    same _require pattern already approved for the Shufersal and Rami Levy
    Online normalizers. Only one of the four guarded fields is exercised
    here; this test only needs to prove the Standard normalizer wires the
    guard, not re-validate the guard's own design."""
    item_with_missing_price = replace(_BASE_ITEM, item_price=None)

    with pytest.raises(ValueError):
        normalize_standard_item(item_with_missing_price, collected_at=_COLLECTED_AT)
