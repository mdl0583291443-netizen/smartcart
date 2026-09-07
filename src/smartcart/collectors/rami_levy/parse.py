"""Parsing for Rami Levy Stores and PriceFull XML.

Parsing only: turns transport-normalized XML bytes into source-faithful
Raw dataclasses (see records.py). Performs no business normalization, no
unit conversion, no numeric coercion, and preserves literal source strings
(including the "לא ידוע" placeholder) verbatim.

Unlike Shufersal's XML (UTF-8 with BOM), Rami Levy's Stores file is UTF-16
LE with a BOM and PriceFull is UTF-8 with a BOM; neither has an <?xml?>
declaration. No manual BOM stripping is done here: `xml.etree.ElementTree`
natively detects a UTF-16 or UTF-8 BOM (or assumes UTF-8 if none is
present) when fed raw bytes directly, and raises ElementTree.ParseError on
anything it cannot decode/parse -- which is exactly the "malformed/
undecodable content fails at parse stage" behavior required here, without
this module needing its own encoding-detection logic.

Targeted live-variant reconnaissance (see docs/adr/0007) found PriceFull
is published under two structurally distinct XML schemas, distinguished
unambiguously by root-level ID tag casing:

- "standard": <ChainID>/<SubChainID>/<StoreID>, a 17-tag Item schema.
  Observed for 98 of 99 stores.
- "online": <ChainId>/<SubChainId>/<StoreId>, a different 16-tag Item
  schema (several fields renamed, LastSaleDateTime absent entirely).
  Observed only for StoreID 039 (the sole StoreType=2 store) to date.

Schema-family detection happens HERE, from the parsed XML structure
itself -- never from the store_id being requested or the filename shape
that led to discovery (see discovery.py, which only ever supplies
filename-shape metadata as a hint, and run.py, which never branches on
store_id). A PriceFull document matching neither known root-tag pattern is
an explicit parse failure, never a guess or a fuzzy field-by-field
fallback.

Root-tag-based family detection is only safe to rely on because each
family-specific parser is itself strict about its Item-level tags: every
one of the family's known required tags must be *present* as an element
on every <Item> (see `_required_text`), or parsing raises ParseError. A
tag being present with empty/self-closing text is still fine (that is a
legitimate observed value, e.g. <ItemStatus />) -- only the tag's outright
absence is treated as schema drift. An unexpected *extra* tag on an <Item>
is tolerated and simply ignored, since the known field set is read by
name, not inferred from whatever tags happen to be present.

This module is Rami-Levy-specific by design -- there is no generic
cross-chain parser abstraction.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
    RamiLevyStoreRaw,
)


class ParseError(Exception):
    """Raised when Rami Levy XML cannot be parsed, decoded, or (for
    PriceFull) matched to a known schema family."""


def _parse_xml(data: bytes, *, context: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"Malformed/undecodable {context} XML: {exc}") from exc


def _text(element: ET.Element, tag: str) -> str | None:
    """Source-faithful text lookup: unlike Element.findtext(), which
    returns '' for a found-but-empty/self-closing element and only falls
    back to a default when the tag is entirely absent, this returns None
    for both cases so "missing" and "present but empty" are not silently
    coerced to an empty string. A genuinely non-empty value -- including
    the literal placeholder "לא ידוע" -- is returned exactly as-is.

    Used for root-level file-context fields and for Stores parsing, where
    an absent tag is not treated as schema drift. For Item-level PriceFull
    fields, see `_required_text` instead: those tags are required to be
    *present* (fail closed if not), even though their text may be empty.
    """
    child = element.find(tag)
    if child is None or not child.text:
        return None
    return child.text


def _required_text(element: ET.Element, tag: str, *, family: str) -> str | None:
    """Look up a required Item-level child tag's text.

    Raises ParseError if the tag element itself is entirely absent from
    `element` -- a known required Item-level tag missing from the source
    is schema drift and must fail closed, never silently become None.
    Returns None (not an error) if the tag IS present but has empty/no
    text, since that is a legitimate observed source state (e.g. a
    self-closing <ItemStatus />) -- distinct from the tag being absent.
    """
    child = element.find(tag)
    if child is None:
        raise ParseError(f"Missing required <{tag}> tag in {family} PriceFull Item element.")
    return child.text if child.text else None


def schema_family_of(
    items: list[RamiLevyPriceItemRawStandard] | list[RamiLevyPriceItemRawOnline],
) -> str | None:
    """Return "standard" or "online" for a non-empty parsed Item list, or
    None if the list is empty (nothing to inspect). This is the single
    place that maps a Raw dataclass type back to its family name, so
    validate.py and run.py never re-derive the mapping independently."""
    if not items:
        return None
    return "online" if isinstance(items[0], RamiLevyPriceItemRawOnline) else "standard"


def parse_stores_xml(data: bytes) -> list[RamiLevyStoreRaw]:
    """Parse a transport-normalized Rami Levy Stores XML document.

    Returns one RamiLevyStoreRaw per <Store> element found, in document
    order, carrying the ChainID/ChainName/SubChainID/SubChainName each
    store was nested under. Returns an empty list for a structurally valid
    document with zero stores -- callers must not conflate "valid XML,
    zero records" with a parse failure (see validate.py for that check).
    """
    root = _parse_xml(data, context="Stores")
    chain_id = _text(root, "ChainID") or ""
    chain_name = _text(root, "ChainName")

    stores: list[RamiLevyStoreRaw] = []
    for subchain in root.findall(".//SubChain"):
        subchain_id = _text(subchain, "SubChainID") or ""
        subchain_name = _text(subchain, "SubChainName")
        for store in subchain.findall("./Stores/Store"):
            stores.append(
                RamiLevyStoreRaw(
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
                    zip_code=_text(store, "ZipCode"),
                )
            )
    return stores


def parse_pricefull_xml(
    data: bytes,
) -> list[RamiLevyPriceItemRawStandard] | list[RamiLevyPriceItemRawOnline]:
    """Parse a transport-normalized Rami Levy PriceFull XML document.

    Detects the schema family from root-level ID tag casing (see module
    docstring) and returns the matching family's Raw dataclass list.
    Raises ParseError if the document's root matches neither known schema.
    Returns an empty list for a structurally valid, recognized-schema
    document with zero items.
    """
    root = _parse_xml(data, context="PriceFull")

    if root.find("ChainID") is not None:
        return _parse_pricefull_standard(root)
    if root.find("ChainId") is not None:
        return _parse_pricefull_online(root)

    raise ParseError(
        "Unrecognized PriceFull schema: root element has neither the standard "
        "(ChainID/SubChainID/StoreID) nor the online (ChainId/SubChainId/StoreId) "
        "identifying tags. Refusing to guess a field mapping."
    )


def _pricefull_items(root: ET.Element) -> list[ET.Element]:
    items_container = root.find("Items")
    return items_container.findall("Item") if items_container is not None else []


def _parse_pricefull_standard(root: ET.Element) -> list[RamiLevyPriceItemRawStandard]:
    chain_id = _text(root, "ChainID") or ""
    subchain_id = _text(root, "SubChainID") or ""
    store_id = _text(root, "StoreID") or ""
    bikoret_no = _text(root, "BikoretNo")

    items: list[RamiLevyPriceItemRawStandard] = []
    for item in _pricefull_items(root):
        items.append(
            RamiLevyPriceItemRawStandard(
                chain_id=chain_id,
                subchain_id=subchain_id,
                store_id=store_id,
                bikoret_no=bikoret_no,
                price_update_time=_required_text(item, "PriceUpdateTime", family="standard"),
                item_code=_required_text(item, "ItemCode", family="standard") or "",
                last_sale_date_time=_required_text(item, "LastSaleDateTime", family="standard"),
                item_type=_required_text(item, "ItemType", family="standard"),
                item_name=_required_text(item, "ItemName", family="standard"),
                manufacture_name=_required_text(item, "ManufactureName", family="standard"),
                manufacture_country=_required_text(item, "ManufactureCountry", family="standard"),
                manufacture_item_description=_required_text(
                    item, "ManufactureItemDescription", family="standard"
                ),
                unit_qty=_required_text(item, "UnitQty", family="standard"),
                quantity=_required_text(item, "Quantity", family="standard"),
                unit_of_measure=_required_text(item, "UnitOfMeasure", family="standard"),
                is_weighted=_required_text(item, "bIsWeighted", family="standard"),
                qty_in_package=_required_text(item, "QtyInPackage", family="standard"),
                item_price=_required_text(item, "ItemPrice", family="standard"),
                unit_of_measure_price=_required_text(item, "UnitOfMeasurePrice", family="standard"),
                allow_discount=_required_text(item, "AllowDiscount", family="standard"),
                item_status=_required_text(item, "ItemStatus", family="standard"),
            )
        )
    return items


def _parse_pricefull_online(root: ET.Element) -> list[RamiLevyPriceItemRawOnline]:
    chain_id = _text(root, "ChainId") or ""
    subchain_id = _text(root, "SubChainId") or ""
    store_id = _text(root, "StoreId") or ""
    bikoret_no = _text(root, "BikoretNo")

    items: list[RamiLevyPriceItemRawOnline] = []
    for item in _pricefull_items(root):
        items.append(
            RamiLevyPriceItemRawOnline(
                chain_id=chain_id,
                subchain_id=subchain_id,
                store_id=store_id,
                bikoret_no=bikoret_no,
                price_update_date=_required_text(item, "PriceUpdateDate", family="online"),
                item_code=_required_text(item, "ItemCode", family="online") or "",
                item_type=_required_text(item, "ItemType", family="online"),
                item_nm=_required_text(item, "ItemNm", family="online"),
                manufacturer_name=_required_text(item, "ManufacturerName", family="online"),
                manufacture_country=_required_text(item, "ManufactureCountry", family="online"),
                manufacturer_item_description=_required_text(
                    item, "ManufacturerItemDescription", family="online"
                ),
                unit_qty=_required_text(item, "UnitQty", family="online"),
                quantity=_required_text(item, "Quantity", family="online"),
                unit_of_measure=_required_text(item, "UnitOfMeasure", family="online"),
                is_weighted=_required_text(item, "bIsWeighted", family="online"),
                qty_in_package=_required_text(item, "QtyInPackage", family="online"),
                item_price=_required_text(item, "ItemPrice", family="online"),
                unit_of_measure_price=_required_text(item, "UnitOfMeasurePrice", family="online"),
                allow_discount=_required_text(item, "AllowDiscount", family="online"),
                item_status=_required_text(item, "ItemStatus", family="online"),
            )
        )
    return items
