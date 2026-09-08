"""FIRST RED tests proving the not-yet-implemented common normalization
contract (see test_shufersal_normalize.py for the full 7-case matrix) also
applies -- independently -- to Rami Levy's PriceFull "online" schema family
(docs/adr/0007), using the same real matched Coke product used for
Shufersal's multipack case.

This module tests CROSS-RETAILER STRUCTURAL COMPATIBILITY ONLY: that two
structurally different retailer records each normalize, on their own, into
the same NormalizedPriceItem contract shape. It deliberately does NOT test
or implement global product identity, cross-retailer SKU matching, merging
of the two results, or any decision that they represent the same
real-world product -- that belongs to a future Product Matching phase. The
two normalized results below are compared only for field-set shape, never
for value equality with each other.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

from smartcart.collectors.rami_levy.records import RamiLevyPriceItemRawOnline
from smartcart.collectors.shufersal.records import ShufersalPriceItemRaw
from smartcart.normalize.contract import NormalizedPriceItem
from smartcart.normalize.rami_levy import normalize_online_item
from smartcart.normalize.shufersal import normalize_item as normalize_shufersal_item

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

# Real Rami Levy chain GLN (7290058140886) and the online-family StoreId
# shape ("39", unpadded -- see docs/adr/0007), consistent with the base
# fixtures already used by tests/collectors/rami_levy/test_validate.py.
_RAMI_LEVY_ONLINE_COKE = RamiLevyPriceItemRawOnline(
    chain_id="7290058140886",
    subchain_id="1",
    store_id="39",
    bikoret_no="3",
    price_update_date="2026-09-04 06:23:00",
    item_code="7290004125030",
    item_type="1",
    item_nm="מארז קוקה קולה 6 פחיות",
    manufacturer_name="קוקה קולה ישראל",
    manufacture_country="IL",
    # Deliberately different from item_nm: proves product_name is sourced
    # from ItemNm, not ManufacturerItemDescription (neither of which is
    # part of the common normalized contract in any case).
    manufacturer_item_description="DECOY - must not appear in product_name",
    unit_qty="Liter",
    quantity="1.98",
    unit_of_measure="1.98 Liter",
    is_weighted="0",
    qty_in_package="לא ידוע",
    item_price="24.90",
    unit_of_measure_price="12.58",
    allow_discount="1",
    item_status=None,
)

_SHUFERSAL_COKE = ShufersalPriceItemRaw(
    chain_id="7290027600007",
    subchain_id="002",
    store_id="413",
    bikoret_no="0",
    price_update_time="2026-09-04T06:23:00",
    item_code="7290004125030",
    last_sale_date_time="2026-09-04T00:00:00",
    item_type="1",
    item_name='קוקה קולה 6*330 מ"ל',
    manufacture_name="קוקה קולה ישראל",
    manufacture_country="IL",
    manufacture_item_description='קוקה קולה 6*330 מ"ל',
    unit_qty="Liter",
    quantity="1.98",
    unit_of_measure="1.98 Liter",
    is_weighted="0",
    qty_in_package="6",
    item_price="23.90",
    unit_of_measure_price="12.07",
    allow_discount="1",
    item_status=None,
)


def test_rami_levy_online_schema_normalizes_into_the_common_contract() -> None:
    """The online family's differently-named fields (ItemNm, not ItemName;
    ManufacturerName, not ManufactureName; PriceUpdateDate, not
    PriceUpdateTime; no LastSaleDateTime at all) still map onto the exact
    same common contract as Shufersal's."""
    normalized = normalize_online_item(_RAMI_LEVY_ONLINE_COKE, collected_at=_COLLECTED_AT)

    assert isinstance(normalized, NormalizedPriceItem)
    assert normalized.retailer_chain_id == "7290058140886"
    assert normalized.retailer_item_id == "7290004125030"
    assert normalized.store_id == "39"
    assert normalized.published_price == Decimal("24.90")
    assert normalized.published_price_raw == "24.90"
    assert normalized.declared_quantity == Decimal("1.98")
    assert normalized.declared_quantity_raw == "1.98"
    assert normalized.declared_quantity_unit_raw == "Liter"
    assert normalized.is_weighted is False
    # ItemNm != ManufacturerItemDescription on this fixture -- pins
    # product_name to ItemNm specifically.
    assert normalized.product_name == "מארז קוקה קולה 6 פחיות"
    assert normalized.product_name == _RAMI_LEVY_ONLINE_COKE.item_nm
    assert normalized.collected_at == _COLLECTED_AT
    assert {f.name for f in dataclasses.fields(normalized)} == _CONTRACT_FIELD_NAMES


def test_shufersal_and_rami_levy_online_normalize_independently_into_the_same_contract_shape() -> (
    None
):
    """Cross-retailer structural proof only (see module docstring): both
    records normalize independently into NormalizedPriceItem with the
    exact same field set. Their product names are asserted to remain
    each retailer's own distinct source text -- never merged, matched, or
    compared to each other."""
    shufersal_normalized = normalize_shufersal_item(_SHUFERSAL_COKE, collected_at=_COLLECTED_AT)
    rami_levy_normalized = normalize_online_item(_RAMI_LEVY_ONLINE_COKE, collected_at=_COLLECTED_AT)

    assert isinstance(shufersal_normalized, NormalizedPriceItem)
    assert isinstance(rami_levy_normalized, NormalizedPriceItem)
    assert {f.name for f in dataclasses.fields(shufersal_normalized)} == _CONTRACT_FIELD_NAMES
    assert {f.name for f in dataclasses.fields(rami_levy_normalized)} == _CONTRACT_FIELD_NAMES

    assert shufersal_normalized.product_name == 'קוקה קולה 6*330 מ"ל'
    assert rami_levy_normalized.product_name == "מארז קוקה קולה 6 פחיות"
