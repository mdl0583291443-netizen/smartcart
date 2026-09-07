"""Tests for smartcart.collectors.rami_levy.parse.

All deterministic, no network access. Fixtures are synthetic XML matching
the exact tag names/casing verified directly from Rami Levy reconnaissance
evidence (e.g. root tag "Root" for both file types, "ZipCode" -- not
Shufersal's "ZIPCode" -- and, for the online schema family, "ChainId"/
"SubChainId"/"StoreId"/"ItemNm"/"ManufacturerName"/"PriceUpdateDate") --
not copies of any real downloaded file.
"""

from __future__ import annotations

import dataclasses

import pytest

from smartcart.collectors.rami_levy.parse import (
    ParseError,
    parse_pricefull_xml,
    parse_stores_xml,
    schema_family_of,
)
from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
)

# UTF-16 LE with BOM, no <?xml?> declaration -- matches observed Stores format.
_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>7290058140886</ChainID>"
    "<ChainName>רמי לוי שיווק השקמה</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "<SubChains><SubChain>"
    "<SubChainID>001</SubChainID>"
    "<SubChainName>1</SubChainName>"
    "<Stores><Store>"
    "<StoreID>039</StoreID>"
    "<BikoretNo>9</BikoretNo>"
    "<StoreType>2</StoreType>"
    "<StoreName>מרלוג אינטרנט</StoreName>"
    "<Address>https://www.rami-levy.co.il/he</Address>"
    "<City>6100</City>"
    "<ZipCode></ZipCode>"
    "</Store></Stores>"
    "</SubChain></SubChains></Root>"
)
VALID_STORES_XML = b"\xff\xfe" + _STORES_XML_TEXT.encode("utf-16-le")

_EMPTY_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>7290058140886</ChainID>"
    "<ChainName>רמי לוי שיווק השקמה</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "<SubChains></SubChains>"
    "</Root>"
)
EMPTY_STORES_XML = b"\xff\xfe" + _EMPTY_STORES_XML_TEXT.encode("utf-16-le")

# UTF-8 with BOM, no <?xml?> declaration -- matches observed standard-family
# PriceFull format.
VALID_PRICEFULL_STANDARD_XML = (
    b"\xef\xbb\xbf"
    b"<Root><ChainID>7290058140886</ChainID><SubChainID>001</SubChainID>"
    b"<StoreID>039</StoreID><BikoretNo>9</BikoretNo><Items>"
    b"<Item>"
    b"<PriceUpdateTime>2026-04-27T11:19:43.000</PriceUpdateTime>"
    b"<ItemCode>7290000139159</ItemCode>"
    b"<LastSaleDateTime>2026-08-19T16:40:12.000</LastSaleDateTime>"
    b"<ItemType>1</ItemType>"
    b"<ItemName>\xd7\x9e\xd7\x95\xd7\xa6\xd7\xa8 \xd7\x91\xd7\x93\xd7\x99\xd7\xa7\xd7\x94"
    b"</ItemName>"
    b"<ManufactureName>\xd7\x9c\xd7\x90 \xd7\x99\xd7\x93\xd7\x95\xd7\xa2</ManufactureName>"
    b"<ManufactureCountry>\xd7\x9c\xd7\x90 \xd7\x99\xd7\x93\xd7\x95\xd7\xa2</ManufactureCountry>"
    b"<ManufactureItemDescription>\xd7\x91\xd7\x93\xd7\x99\xd7\xa7\xd7\x94</ManufactureItemDescription>"
    b"<UnitQty>\xd7\x92\xd7\xa8\xd7\x9d</UnitQty>"
    b"<Quantity>0.00</Quantity>"
    b"<UnitOfMeasure>100 \xd7\x92\xd7\xa8\xd7\x9d</UnitOfMeasure>"
    b"<bIsWeighted>0</bIsWeighted>"
    b"<QtyInPackage>\xd7\x9c\xd7\x90 \xd7\x99\xd7\x93\xd7\x95\xd7\xa2</QtyInPackage>"
    b"<ItemPrice>10.20</ItemPrice>"
    b"<UnitOfMeasurePrice>3.68</UnitOfMeasurePrice>"
    b"<AllowDiscount>1</AllowDiscount>"
    b"<ItemStatus />"
    b"</Item></Items></Root>"
)

EMPTY_PRICEFULL_STANDARD_XML = (
    b"<Root><ChainID>7290058140886</ChainID><SubChainID>001</SubChainID>"
    b"<StoreID>039</StoreID><BikoretNo>9</BikoretNo><Items></Items></Root>"
)

# Matches the online/alternate schema family observed for StoreID 039:
# ChainId/SubChainId/StoreId (not ...ID), StoreId unpadded ("39"), and a
# 16-tag Item schema with PriceUpdateDate/ItemNm/ManufacturerName/
# ManufacturerItemDescription and no LastSaleDateTime at all.
VALID_PRICEFULL_ONLINE_XML = (
    b"\xef\xbb\xbf"
    b"<Root><ChainId>7290058140886</ChainId><SubChainId>1</SubChainId>"
    b"<StoreId>39</StoreId><BikoretNo>3</BikoretNo><Items>"
    b"<Item>"
    b"<PriceUpdateDate>2025-01-19 16:03:55</PriceUpdateDate>"
    b"<ItemCode>6</ItemCode>"
    b"<ItemType>1</ItemType>"
    b"<ItemNm>\xd7\xa4\xd7\xa8\xd7\x99\xd7\x98 \xd7\x97\xd7\x93\xd7\xa9</ItemNm>"
    b"<ManufacturerName>\xd7\x9c\xd7\x90 \xd7\x99\xd7\x93\xd7\x95\xd7\xa2</ManufacturerName>"
    b"<ManufactureCountry>\xd7\x9c\xd7\x90 \xd7\x99\xd7\x93\xd7\x95\xd7\xa2</ManufactureCountry>"
    b"<ManufacturerItemDescription>\xd7\xa4\xd7\xa8\xd7\x99\xd7\x98</ManufacturerItemDescription>"
    b"<UnitQty>\xd7\x99\xd7\x97\xd7\x93\xd7\xa0\xd7\x99\xd7\x9d</UnitQty>"
    b"<Quantity>1</Quantity>"
    b"<UnitOfMeasure>1 \xd7\x99\xd7\x97\xd7\x93\xd7\xa0\xd7\x99\xd7\x9d</UnitOfMeasure>"
    b"<bIsWeighted>0</bIsWeighted>"
    b"<QtyInPackage>6.0000</QtyInPackage>"
    b"<ItemPrice>30.6</ItemPrice>"
    b"<UnitOfMeasurePrice>30.6</UnitOfMeasurePrice>"
    b"<AllowDiscount>1</AllowDiscount>"
    b"<ItemStatus>1</ItemStatus>"
    b"</Item></Items></Root>"
)

EMPTY_PRICEFULL_ONLINE_XML = (
    b"<Root><ChainId>7290058140886</ChainId><SubChainId>1</SubChainId>"
    b"<StoreId>39</StoreId><BikoretNo>3</BikoretNo><Items></Items></Root>"
)

# Neither ChainID/SubChainID/StoreID nor ChainId/SubChainId/StoreId --
# structurally valid XML, but an unrecognized schema.
UNRECOGNIZED_SCHEMA_XML = (
    b"<Root><Chain>7290058140886</Chain><Store>39</Store><Items></Items></Root>"
)

MALFORMED_XML = b"<Root><Unclosed>"

_LA_YADUA = "לא ידוע"  # "unknown" -- the literal placeholder observed in source data


def test_parse_stores_xml_valid_utf16_bom() -> None:
    stores = parse_stores_xml(VALID_STORES_XML)
    assert len(stores) == 1
    store = stores[0]
    assert store.store_id == "039"
    assert store.chain_id == "7290058140886"
    assert store.subchain_id == "001"
    assert store.store_type == "2"
    assert store.address == "https://www.rami-levy.co.il/he"
    assert store.city == "6100"


def test_parse_stores_xml_zip_code_tag_name_and_empty_value() -> None:
    """Source tag is 'ZipCode' (not Shufersal's 'ZIPCode'), and an
    explicitly empty element must come through as None, not ''."""
    store = parse_stores_xml(VALID_STORES_XML)[0]
    assert store.zip_code is None


def test_parse_stores_xml_ids_stay_str_with_padding() -> None:
    store = parse_stores_xml(VALID_STORES_XML)[0]
    assert isinstance(store.store_id, str)
    assert store.store_id == "039"  # zero-padding preserved, not int 39


def test_parse_stores_xml_structurally_valid_but_empty() -> None:
    assert parse_stores_xml(EMPTY_STORES_XML) == []


def test_parse_stores_xml_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_stores_xml(MALFORMED_XML)


# --- Standard PriceFull schema family ---------------------------------


def test_parse_pricefull_standard_schema_returns_standard_dataclass() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert len(items) == 1
    assert isinstance(items[0], RamiLevyPriceItemRawStandard)
    assert schema_family_of(items) == "standard"


def test_parse_pricefull_standard_preserves_fields() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawStandard)
    item = items[0]

    assert item.item_code == "7290000139159"
    assert isinstance(item.item_code, str)
    assert item.item_price == "10.20"
    assert item.unit_of_measure_price == "3.68"
    assert item.chain_id == "7290058140886"
    assert item.subchain_id == "001"
    assert item.store_id == "039"
    assert item.bikoret_no == "9"
    assert item.item_status is None  # self-closing <ItemStatus /> -> no text
    assert item.last_sale_date_time == "2026-08-19T16:40:12.000"


def test_parse_pricefull_standard_preserves_la_yadua_placeholder_verbatim() -> None:
    """The literal 'לא ידוע' (unknown) placeholder must be preserved as a
    real string value, never translated to None -- and definitely never
    reversed/reordered."""
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawStandard)
    item = items[0]
    assert item.manufacture_name == _LA_YADUA
    assert item.manufacture_country == _LA_YADUA
    assert item.qty_in_package == _LA_YADUA
    assert item.qty_in_package is not None
    # Exact logical/storage code-point order, not merely visual equality.
    assert [ord(ch) for ch in item.qty_in_package] == [
        0x05DC,
        0x05D0,
        0x0020,
        0x05D9,
        0x05D3,
        0x05D5,
        0x05E2,
    ]


def test_parse_pricefull_standard_zero_quantity_preserved() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawStandard)
    assert items[0].quantity == "0.00"


def test_parse_pricefull_standard_structurally_valid_but_empty() -> None:
    items = parse_pricefull_xml(EMPTY_PRICEFULL_STANDARD_XML)
    assert items == []
    assert schema_family_of(items) is None


# --- Online/alternate PriceFull schema family -----------------------------


def test_parse_pricefull_online_schema_returns_online_dataclass() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    assert len(items) == 1
    assert isinstance(items[0], RamiLevyPriceItemRawOnline)
    assert schema_family_of(items) == "online"


def test_parse_pricefull_online_preserves_renamed_fields() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawOnline)
    item = items[0]

    assert item.price_update_date == "2025-01-19 16:03:55"
    assert item.item_nm is not None
    assert item.manufacturer_name == _LA_YADUA
    assert item.manufacturer_item_description is not None
    assert item.manufacture_country == _LA_YADUA  # kept its standard spelling


def test_parse_pricefull_online_has_no_last_sale_date_time_field() -> None:
    """The online schema has no LastSaleDateTime source field at all --
    there must be no attribute pretending it exists as always-None."""
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    item = items[0]
    assert not hasattr(item, "last_sale_date_time")


def test_parse_pricefull_online_ids_unpadded_and_str() -> None:
    """XML-carried StoreId is observed unpadded ("39"); it must be
    preserved exactly, not padded or coerced to int."""
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawOnline)
    item = items[0]
    assert item.store_id == "39"
    assert isinstance(item.store_id, str)
    assert item.chain_id == "7290058140886"
    assert item.subchain_id == "1"


def test_parse_pricefull_online_item_status_populated() -> None:
    """Unlike the standard family's sampled self-closing <ItemStatus />,
    the online family was observed with a real, non-empty ItemStatus."""
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawOnline)
    assert items[0].item_status == "1"


def test_parse_pricefull_online_qty_in_package_is_numeric_here() -> None:
    """Unlike the standard family's sampled 'לא ידוע' QtyInPackage, the
    online family was observed with a real decimal value -- both are
    valid observed source states and neither is special-cased."""
    items = parse_pricefull_xml(VALID_PRICEFULL_ONLINE_XML)
    assert isinstance(items[0], RamiLevyPriceItemRawOnline)
    assert items[0].qty_in_package == "6.0000"


def test_parse_pricefull_online_structurally_valid_but_empty() -> None:
    items = parse_pricefull_xml(EMPTY_PRICEFULL_ONLINE_XML)
    assert items == []
    assert schema_family_of(items) is None


# --- Schema detection is content-based, not store/filename-based ---------


def test_parse_pricefull_unrecognized_schema_raises_parse_error() -> None:
    """Structurally valid XML that matches neither known root-tag pattern
    must fail explicitly, never fall back to a guessed field mapping."""
    with pytest.raises(ParseError):
        parse_pricefull_xml(UNRECOGNIZED_SCHEMA_XML)


def test_parse_pricefull_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_pricefull_xml(MALFORMED_XML)


def test_parse_pricefull_undecodable_bytes_raise_parse_error() -> None:
    """Non-UTF-8, non-BOM-marked byte sequences must fail loudly at parse
    stage rather than silently producing mojibake."""
    undecodable = "<Root><Name>שלום</Name></Root>".encode("cp1255")
    with pytest.raises(ParseError):
        parse_pricefull_xml(undecodable)


def test_parse_pricefull_non_gzip_plain_bytes_still_parse() -> None:
    """parse.py has no compression/container concept at all -- whatever
    bytes transport.normalize() hands it (gzip-decompressed, ZIP-member-
    extracted, or passed through unchanged) must parse the same way."""
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert len(items) == 1


# --- Fail-closed on a missing required Item-level tag ---------------------
#
# Root-tag-based family detection (ChainID vs ChainId) is only safe because
# each family parser is itself strict: every known required Item-level tag
# must be *present* on every <Item>, or parsing raises ParseError. This is
# distinct from a tag being present with empty/self-closing text (already
# covered above, e.g. ItemStatus) -- only outright absence is schema drift.

_STANDARD_MISSING_ITEM_NAME_XML = VALID_PRICEFULL_STANDARD_XML.replace(
    b"<ItemName>\xd7\x9e\xd7\x95\xd7\xa6\xd7\xa8 \xd7\x91\xd7\x93\xd7\x99\xd7\xa7\xd7\x94"
    b"</ItemName>",
    b"",
)

_ONLINE_MISSING_ITEM_NM_XML = VALID_PRICEFULL_ONLINE_XML.replace(
    b"<ItemNm>\xd7\xa4\xd7\xa8\xd7\x99\xd7\x98 \xd7\x97\xd7\x93\xd7\xa9</ItemNm>", b""
)

_STANDARD_EXTRA_TAG_XML = VALID_PRICEFULL_STANDARD_XML.replace(
    b"</Item></Items></Root>",
    b"<UnexpectedFutureTag>surprise</UnexpectedFutureTag></Item></Items></Root>",
)

_ONLINE_EXTRA_TAG_XML = VALID_PRICEFULL_ONLINE_XML.replace(
    b"</Item></Items></Root>",
    b"<UnexpectedFutureTag>surprise</UnexpectedFutureTag></Item></Items></Root>",
)


def test_parse_pricefull_standard_missing_required_tag_raises_parse_error() -> None:
    """(A) Correct standard root/schema-family casing, but ItemName is
    entirely absent from the Item -- must fail closed, not become None."""
    assert b"<ItemName>" not in _STANDARD_MISSING_ITEM_NAME_XML  # sanity: tag truly gone
    with pytest.raises(ParseError):
        parse_pricefull_xml(_STANDARD_MISSING_ITEM_NAME_XML)


def test_parse_pricefull_online_missing_required_tag_raises_parse_error() -> None:
    """(B) Correct online root/schema-family casing, but ItemNm is
    entirely absent from the Item -- must fail closed, not become None."""
    assert b"<ItemNm>" not in _ONLINE_MISSING_ITEM_NM_XML  # sanity: tag truly gone
    with pytest.raises(ParseError):
        parse_pricefull_xml(_ONLINE_MISSING_ITEM_NM_XML)


def test_parse_pricefull_standard_extra_unexpected_tag_is_tolerated() -> None:
    """(C) All required standard tags present, plus one unexpected extra
    Item tag -- parsing succeeds, the extra tag is ignored, and the raw
    field set is exactly the documented standard field set (unchanged)."""
    items = parse_pricefull_xml(_STANDARD_EXTRA_TAG_XML)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RamiLevyPriceItemRawStandard)

    field_names = {f.name for f in dataclasses.fields(item)}
    assert field_names == {
        "chain_id",
        "subchain_id",
        "store_id",
        "bikoret_no",
        "price_update_time",
        "item_code",
        "last_sale_date_time",
        "item_type",
        "item_name",
        "manufacture_name",
        "manufacture_country",
        "manufacture_item_description",
        "unit_qty",
        "quantity",
        "unit_of_measure",
        "is_weighted",
        "qty_in_package",
        "item_price",
        "unit_of_measure_price",
        "allow_discount",
        "item_status",
    }
    assert not hasattr(item, "UnexpectedFutureTag")
    assert not hasattr(item, "unexpected_future_tag")
    # Untouched fields still round-trip correctly.
    assert item.item_code == "7290000139159"


def test_parse_pricefull_online_extra_unexpected_tag_is_tolerated() -> None:
    """(D) All required online tags present, plus one unexpected extra
    Item tag -- parsing succeeds, the extra tag is ignored, and the raw
    field set is exactly the documented online field set (unchanged)."""
    items = parse_pricefull_xml(_ONLINE_EXTRA_TAG_XML)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RamiLevyPriceItemRawOnline)

    field_names = {f.name for f in dataclasses.fields(item)}
    assert field_names == {
        "chain_id",
        "subchain_id",
        "store_id",
        "bikoret_no",
        "price_update_date",
        "item_code",
        "item_type",
        "item_nm",
        "manufacturer_name",
        "manufacture_country",
        "manufacturer_item_description",
        "unit_qty",
        "quantity",
        "unit_of_measure",
        "is_weighted",
        "qty_in_package",
        "item_price",
        "unit_of_measure_price",
        "allow_discount",
        "item_status",
    }
    assert not hasattr(item, "UnexpectedFutureTag")
    assert not hasattr(item, "unexpected_future_tag")
    assert "last_sale_date_time" not in field_names
    # Untouched fields still round-trip correctly.
    assert item.item_code == "6"


def test_parse_pricefull_standard_present_but_empty_tag_still_succeeds() -> None:
    """Contrast with the missing-tag case: a tag that IS present but has
    no/empty text (self-closing) is a legitimate value, not schema drift,
    and must not raise. ItemStatus already covers this above; this checks
    it explicitly for the same fixture used in the missing-tag tests."""
    items = parse_pricefull_xml(VALID_PRICEFULL_STANDARD_XML)
    assert items[0].item_status is None
