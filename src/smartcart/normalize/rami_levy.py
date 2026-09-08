"""Rami Levy PriceFull (online and standard schema families) -> common
normalized contract mapping.

Direct field mapping only, per the frozen contract's authoritative source
mapping for Rami Levy Online:

    product_name <- ItemNm
    published_price_raw <- ItemPrice; published_price <- Decimal(ItemPrice)
    declared_quantity_raw <- Quantity; declared_quantity <- Decimal(Quantity)
    declared_quantity_unit_raw <- UnitQty
    is_weighted <- bIsWeighted, passed through directly ("1" -> True,
        "0" -> False, absent -> None)

No parsing, unit conversion, pack-composition inference, or enrichment
happens here. UnitOfMeasure, UnitOfMeasurePrice, QtyInPackage,
AllowDiscount, and ManufacturerItemDescription are not read at all.

normalize_standard_item, for the "standard" schema family, follows the
same direct-mapping approach, using the same 17-tag Item schema field
names as Shufersal's:

    product_name <- ItemName
    published_price_raw <- ItemPrice; published_price <- Decimal(ItemPrice)
    declared_quantity_raw <- Quantity; declared_quantity <- Decimal(Quantity)
    declared_quantity_unit_raw <- UnitQty
    is_weighted <- bIsWeighted, passed through directly ("1" -> True,
        "0" -> False, absent -> None)

UnitOfMeasure, UnitOfMeasurePrice, QtyInPackage, AllowDiscount,
ManufactureItemDescription, and LastSaleDateTime are not read at all.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
)
from smartcart.normalize.contract import NormalizedPriceItem


def _require(value: str | None, field: str) -> str:
    if value is None:
        raise ValueError(
            f"normalization contract violation: required field {field!r} "
            f"was None; upstream validation should have prevented this"
        )
    return value


def normalize_online_item(
    raw: RamiLevyPriceItemRawOnline, *, collected_at: datetime
) -> NormalizedPriceItem:
    item_price = _require(raw.item_price, "ItemPrice")
    quantity = _require(raw.quantity, "Quantity")
    unit_qty = _require(raw.unit_qty, "UnitQty")
    item_nm = _require(raw.item_nm, "ItemNm")

    return NormalizedPriceItem(
        retailer_chain_id=raw.chain_id,
        retailer_item_id=raw.item_code,
        store_id=raw.store_id,
        published_price=Decimal(item_price),
        published_price_raw=item_price,
        declared_quantity=Decimal(quantity),
        declared_quantity_raw=quantity,
        declared_quantity_unit_raw=unit_qty,
        is_weighted=None if raw.is_weighted is None else raw.is_weighted == "1",
        product_name=item_nm,
        collected_at=collected_at,
    )


def normalize_standard_item(
    raw: RamiLevyPriceItemRawStandard, *, collected_at: datetime
) -> NormalizedPriceItem:
    item_price = _require(raw.item_price, "ItemPrice")
    quantity = _require(raw.quantity, "Quantity")
    unit_qty = _require(raw.unit_qty, "UnitQty")
    item_name = _require(raw.item_name, "ItemName")

    return NormalizedPriceItem(
        retailer_chain_id=raw.chain_id,
        retailer_item_id=raw.item_code,
        store_id=raw.store_id,
        published_price=Decimal(item_price),
        published_price_raw=item_price,
        declared_quantity=Decimal(quantity),
        declared_quantity_raw=quantity,
        declared_quantity_unit_raw=unit_qty,
        is_weighted=None if raw.is_weighted is None else raw.is_weighted == "1",
        product_name=item_name,
        collected_at=collected_at,
    )
