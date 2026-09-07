"""Tests for smartcart.collectors.shufersal.parse.

All deterministic, no network access. Fixtures below are synthetic XML
constructed to match the Shufersal element schema observed in
reconnaissance (tag names only) -- not copies of any real downloaded file.
"""

from __future__ import annotations

import pytest

from smartcart.collectors.shufersal.parse import ParseError, parse_pricefull_xml, parse_stores_xml

VALID_STORES_XML = (
    b"\xef\xbb\xbf"
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<Chain>"
    b"<ChainID>7290027600007</ChainID>"
    b"<ChainName>Test Chain</ChainName>"
    b"<LastUpdateDate>2026-09-07</LastUpdateDate>"
    b"<LastUpdateTime>02:01:01</LastUpdateTime>"
    b"<SubChains><SubChain>"
    b"<SubChainID>1</SubChainID>"
    b"<SubChainName>Test Sub</SubChainName>"
    b"<Stores><Store>"
    b"<StoreID>756</StoreID>"
    b"<BikoretNo>7</BikoretNo>"
    b"<StoreType>1</StoreType>"
    b"<StoreName>Test Store</StoreName>"
    b"<Address>Test Address 1</Address>"
    b"<City>2530</City>"
    b"<ZIPCode>7030336</ZIPCode>"
    b"</Store></Stores>"
    b"</SubChain></SubChains></Chain>"
)

EMPTY_STORES_XML = (
    b"<Chain>"
    b"<ChainID>7290027600007</ChainID>"
    b"<ChainName>Test Chain</ChainName>"
    b"<LastUpdateDate>2026-09-07</LastUpdateDate>"
    b"<LastUpdateTime>02:01:01</LastUpdateTime>"
    b"<SubChains></SubChains>"
    b"</Chain>"
)

VALID_PRICEFULL_XML = (
    b"\xef\xbb\xbf"
    b"<Root>"
    b"<ChainID>7290027600007</ChainID>"
    b"<SubChainID>002</SubChainID>"
    b"<StoreID>413</StoreID>"
    b"<BikoretNo>0</BikoretNo>"
    b"<Items><Item>"
    b"<PriceUpdateTime>2026-09-04T06:23:00</PriceUpdateTime>"
    b"<ItemCode>10181040009</ItemCode>"
    b"<LastSaleDateTime>2026-09-04T00:00:00</LastSaleDateTime>"
    b"<ItemType>1</ItemType>"
    b"<ItemName>Test Item</ItemName>"
    b"<ManufactureName>Acme</ManufactureName>"
    b"<ManufactureCountry>IL</ManufactureCountry>"
    b"<ManufactureItemDescription>Test Item</ManufactureItemDescription>"
    b"<UnitQty>Gram</UnitQty>"
    b"<Quantity>100.00</Quantity>"
    b"<UnitOfMeasure>100 Gram</UnitOfMeasure>"
    b"<bIsWeighted>0</bIsWeighted>"
    b"<QtyInPackage>1</QtyInPackage>"
    b"<ItemPrice>46.50</ItemPrice>"
    b"<UnitOfMeasurePrice>46.50</UnitOfMeasurePrice>"
    b"<AllowDiscount>1</AllowDiscount>"
    b"<ItemStatus />"
    b"</Item></Items></Root>"
)

EMPTY_PRICEFULL_XML = (
    b"<Root>"
    b"<ChainID>7290027600007</ChainID>"
    b"<SubChainID>002</SubChainID>"
    b"<StoreID>413</StoreID>"
    b"<BikoretNo>0</BikoretNo>"
    b"<Items></Items>"
    b"</Root>"
)

MALFORMED_XML = b"<Root><Unclosed>"


def test_parse_stores_xml_valid() -> None:
    stores = parse_stores_xml(VALID_STORES_XML)
    assert len(stores) == 1
    store = stores[0]
    assert store.store_id == "756"
    assert store.chain_id == "7290027600007"
    assert store.subchain_id == "1"
    assert store.store_name == "Test Store"
    assert store.address == "Test Address 1"
    assert store.city == "2530"
    assert store.zip_code == "7030336"


def test_parse_stores_xml_ids_stay_str() -> None:
    store = parse_stores_xml(VALID_STORES_XML)[0]
    assert isinstance(store.store_id, str)
    assert isinstance(store.chain_id, str)
    assert isinstance(store.subchain_id, str)


def test_parse_stores_xml_handles_bom_and_declaration() -> None:
    # VALID_STORES_XML already has a leading BOM + <?xml?> declaration.
    stores = parse_stores_xml(VALID_STORES_XML)
    assert len(stores) == 1


def test_parse_stores_xml_structurally_valid_but_empty() -> None:
    stores = parse_stores_xml(EMPTY_STORES_XML)
    assert stores == []


def test_parse_stores_xml_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_stores_xml(MALFORMED_XML)


def test_parse_pricefull_xml_valid_preserves_fields() -> None:
    items = parse_pricefull_xml(VALID_PRICEFULL_XML)
    assert len(items) == 1
    item = items[0]

    assert item.item_code == "10181040009"
    assert item.item_name == "Test Item"
    assert item.manufacture_name == "Acme"
    assert item.manufacture_country == "IL"
    assert item.unit_qty == "Gram"
    assert item.quantity == "100.00"
    assert item.unit_of_measure == "100 Gram"
    assert item.is_weighted == "0"
    assert item.qty_in_package == "1"
    assert item.item_price == "46.50"
    assert item.unit_of_measure_price == "46.50"
    assert item.allow_discount == "1"
    assert item.item_status is None  # self-closing <ItemStatus /> -> no text
    assert item.chain_id == "7290027600007"
    assert item.subchain_id == "002"
    assert item.store_id == "413"
    assert item.bikoret_no == "0"


def test_parse_pricefull_xml_numeric_looking_fields_stay_str() -> None:
    item = parse_pricefull_xml(VALID_PRICEFULL_XML)[0]
    assert isinstance(item.item_code, str)
    assert isinstance(item.item_price, str)
    assert isinstance(item.unit_of_measure_price, str)
    assert isinstance(item.quantity, str)
    assert isinstance(item.qty_in_package, str)
    assert isinstance(item.subchain_id, str)
    assert item.subchain_id == "002"  # zero-padding preserved, not coerced to int


def test_parse_pricefull_xml_handles_bom_and_no_declaration() -> None:
    # VALID_PRICEFULL_XML has a leading BOM and (per recon) no <?xml?> decl.
    items = parse_pricefull_xml(VALID_PRICEFULL_XML)
    assert len(items) == 1


def test_parse_pricefull_xml_structurally_valid_but_empty() -> None:
    items = parse_pricefull_xml(EMPTY_PRICEFULL_XML)
    assert items == []


def test_parse_pricefull_xml_malformed_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_pricefull_xml(MALFORMED_XML)
