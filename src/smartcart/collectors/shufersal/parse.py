"""Parsing for Shufersal Stores and PriceFull XML.

Parsing only: turns decompressed XML bytes into source-faithful Raw
dataclasses (see records.py). Performs no business normalization, no unit
conversion, no numeric coercion, and no ItemCode-length-based
classification. This module is Shufersal-specific by design -- there is no
generic cross-chain parser abstraction.

Reconnaissance observed a UTF-8 BOM on both file types and no <?xml?>
declaration on PriceFull files; this module strips a leading UTF-8 BOM if
present and does not require a declaration. It locates records by
structural search (`.//SubChain`, `Items/Item`) rather than assuming a
fixed root element name, since the two file types use different root tags
("Chain" for Stores, "Root" for PriceFull).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from smartcart.collectors.shufersal.records import ShufersalPriceItemRaw, ShufersalStoreRaw

_UTF8_BOM = b"\xef\xbb\xbf"


class ParseError(Exception):
    """Raised when Shufersal XML cannot be parsed."""


def _strip_bom(data: bytes) -> bytes:
    return data[len(_UTF8_BOM) :] if data.startswith(_UTF8_BOM) else data


def _parse_xml(data: bytes, *, context: str) -> ET.Element:
    try:
        return ET.fromstring(_strip_bom(data))
    except ET.ParseError as exc:
        raise ParseError(f"Malformed {context} XML: {exc}") from exc


def _text(element: ET.Element, tag: str) -> str | None:
    """Source-faithful text lookup: unlike Element.findtext(), which
    returns '' for a found-but-empty/self-closing element (e.g.
    <ItemStatus />) and only falls back to a default when the tag is
    entirely absent, this returns None for both cases so "missing" and
    "present but empty" are not silently coerced to an empty string."""
    child = element.find(tag)
    if child is None or not child.text:
        return None
    return child.text


def parse_stores_xml(data: bytes) -> list[ShufersalStoreRaw]:
    """Parse a decompressed Shufersal Stores XML document.

    Returns one ShufersalStoreRaw per <Store> element found, in document
    order, carrying the ChainID/ChainName/SubChainID/SubChainName each
    store was nested under. Returns an empty list for a structurally valid
    document with zero stores -- callers must not conflate "valid XML,
    zero records" with a parse failure (see validate.py for that check).
    """
    root = _parse_xml(data, context="Stores")
    chain_id = _text(root, "ChainID") or ""
    chain_name = _text(root, "ChainName")

    stores: list[ShufersalStoreRaw] = []
    for subchain in root.findall(".//SubChain"):
        subchain_id = _text(subchain, "SubChainID") or ""
        subchain_name = _text(subchain, "SubChainName")
        for store in subchain.findall("./Stores/Store"):
            stores.append(
                ShufersalStoreRaw(
                    chain_id=chain_id,
                    chain_name=chain_name,
                    subchain_id=subchain_id,
                    subchain_name=subchain_name,
                    store_id=_text(store, "StoreID") or "",
                    bikoret_no=_text(store, "BikoretNo"),
                    store_type=_text(store, "StoreType"),
                    store_name=_text(store, "StoreName"),
                    address=_text(store, "Address"),
                    city=_text(store, "City"),
                    zip_code=_text(store, "ZIPCode"),
                )
            )
    return stores


def parse_pricefull_xml(data: bytes) -> list[ShufersalPriceItemRaw]:
    """Parse a decompressed Shufersal PriceFull XML document.

    Returns one ShufersalPriceItemRaw per <Item> element found, carrying
    the file-level ChainID/SubChainID/StoreID/BikoretNo context. Returns an
    empty list for a structurally valid document with zero items.
    """
    root = _parse_xml(data, context="PriceFull")
    chain_id = _text(root, "ChainID") or ""
    subchain_id = _text(root, "SubChainID") or ""
    store_id = _text(root, "StoreID") or ""
    bikoret_no = _text(root, "BikoretNo")

    items_container = root.find("Items")
    item_elements = items_container.findall("Item") if items_container is not None else []

    items: list[ShufersalPriceItemRaw] = []
    for item in item_elements:
        items.append(
            ShufersalPriceItemRaw(
                chain_id=chain_id,
                subchain_id=subchain_id,
                store_id=store_id,
                bikoret_no=bikoret_no,
                price_update_time=_text(item, "PriceUpdateTime"),
                item_code=_text(item, "ItemCode") or "",
                last_sale_date_time=_text(item, "LastSaleDateTime"),
                item_type=_text(item, "ItemType"),
                item_name=_text(item, "ItemName"),
                manufacture_name=_text(item, "ManufactureName"),
                manufacture_country=_text(item, "ManufactureCountry"),
                manufacture_item_description=_text(item, "ManufactureItemDescription"),
                unit_qty=_text(item, "UnitQty"),
                quantity=_text(item, "Quantity"),
                unit_of_measure=_text(item, "UnitOfMeasure"),
                is_weighted=_text(item, "bIsWeighted"),
                qty_in_package=_text(item, "QtyInPackage"),
                item_price=_text(item, "ItemPrice"),
                unit_of_measure_price=_text(item, "UnitOfMeasurePrice"),
                allow_discount=_text(item, "AllowDiscount"),
                item_status=_text(item, "ItemStatus"),
            )
        )
    return items
