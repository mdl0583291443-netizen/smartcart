"""Integration tests for smartcart.collectors.rami_levy.run.

Two clearly separate parts:

1. Offline tests (run by default, no network access) that monkeypatch
   `urllib.request.OpenerDirector.open` with deterministic fake responses
   to exercise run.py's orchestration: run-level login/listing failure,
   end-to-end success, and one PriceFull failure not blocking others.

2. Live tests against the real provider, skipped by default. They only
   run when SMARTCART_LIVE_RAMI_LEVY_TESTS=1 is set, so normal CI never
   fails because the live retailer/provider endpoint is unavailable.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import urllib.request
import zipfile

import pytest

from smartcart.collectors.rami_levy import run
from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
)

BASE_URL = "https://fake.publishedprices.example"
CHAIN_ID = "7290058140886"
SUBCHAIN_ID = "001"
GOOD_STORE = "731"
ONLINE_STORE = "039"
ONLINE_STORE_XML_UNPADDED = "39"
MISSING_STORE = "999"


class _FakeResponse:
    def __init__(self, body: bytes, url: str, status: int = 200) -> None:
        self._body = body
        self._url = url
        self.status = status

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _login_page_html(csrf: str) -> str:
    return f'<html><meta name="csrftoken" content="{csrf}"/><body>login</body></html>'


def _authenticated_file_page_html(csrf: str) -> str:
    return (
        f'<html><meta name="csrftoken" content="{csrf}"/>'
        "<body>Logged in as 'RamiLevi'</body></html>"
    )


def _stores_xml_bytes() -> bytes:
    text = (
        f"<Root><ChainID>{CHAIN_ID}</ChainID><ChainName>Test Chain</ChainName>"
        "<LastUpdateDate>2026-09-07</LastUpdateDate><LastUpdateTime>05:05:00.317</LastUpdateTime>"
        f"<SubChains><SubChain><SubChainID>{SUBCHAIN_ID}</SubChainID><SubChainName>1</SubChainName>"
        f"<Stores><Store><StoreID>{GOOD_STORE}</StoreID><BikoretNo>6</BikoretNo><StoreType>1</StoreType>"
        "<StoreName>Test Store</StoreName><Address>Test Address</Address><City>3000</City>"
        "<ZipCode>9342110</ZipCode></Store></Stores></SubChain></SubChains></Root>"
    )
    return b"\xff\xfe" + text.encode("utf-16-le")  # plain XML, not gzip -- matches observed format


def _pricefull_xml_bytes(store_id: str, n_items: int = 5) -> bytes:
    items = "".join(
        "<Item>"
        "<PriceUpdateTime>2026-04-27T11:19:43.000</PriceUpdateTime>"
        f"<ItemCode>{1000000000000 + i}</ItemCode>"
        "<LastSaleDateTime>2026-08-19T16:40:12.000</LastSaleDateTime>"
        "<ItemType>1</ItemType>"
        f"<ItemName>Test Item {i}</ItemName>"
        "<ManufactureName>Acme</ManufactureName>"
        "<ManufactureCountry>IL</ManufactureCountry>"
        f"<ManufactureItemDescription>Test Item {i}</ManufactureItemDescription>"
        "<UnitQty>Gram</UnitQty><Quantity>100.00</Quantity><UnitOfMeasure>100 Gram</UnitOfMeasure>"
        "<bIsWeighted>0</bIsWeighted><QtyInPackage>1</QtyInPackage>"
        "<ItemPrice>10.20</ItemPrice><UnitOfMeasurePrice>10.20</UnitOfMeasurePrice>"
        "<AllowDiscount>1</AllowDiscount><ItemStatus /></Item>"
        for i in range(n_items)
    )
    text = (
        f"<Root><ChainID>{CHAIN_ID}</ChainID><SubChainID>{SUBCHAIN_ID}</SubChainID>"
        f"<StoreID>{store_id}</StoreID><BikoretNo>0</BikoretNo><Items>{items}</Items></Root>"
    )
    return gzip.compress(b"\xef\xbb\xbf" + text.encode("utf-8"))


def _pricefull_online_xml_bytes(n_items: int = 3) -> bytes:
    """Builds a ZIP-wrapped online-schema PriceFull payload matching the
    exact observed structure: ChainId/SubChainId/StoreId (unpadded "39"),
    a 16-tag Item schema, no LastSaleDateTime."""
    items = "".join(
        "<Item>"
        "<PriceUpdateDate>2025-01-19 16:03:55</PriceUpdateDate>"
        f"<ItemCode>{i + 1}</ItemCode>"
        "<ItemType>1</ItemType>"
        f"<ItemNm>Online Item {i}</ItemNm>"
        "<ManufacturerName>Acme</ManufacturerName>"
        "<ManufactureCountry>IL</ManufactureCountry>"
        f"<ManufacturerItemDescription>Online Item {i}</ManufacturerItemDescription>"
        "<UnitQty>Unit</UnitQty><Quantity>1</Quantity><UnitOfMeasure>1 Unit</UnitOfMeasure>"
        "<bIsWeighted>0</bIsWeighted><QtyInPackage>6.0000</QtyInPackage>"
        "<ItemPrice>30.6</ItemPrice><UnitOfMeasurePrice>30.6</UnitOfMeasurePrice>"
        "<AllowDiscount>1</AllowDiscount><ItemStatus>1</ItemStatus></Item>"
        for i in range(n_items)
    )
    text = (
        f"<Root><ChainId>{CHAIN_ID}</ChainId><SubChainId>{SUBCHAIN_ID.lstrip('0')}</SubChainId>"
        f"<StoreId>{ONLINE_STORE_XML_UNPADDED}</StoreId><BikoretNo>3</BikoretNo>"
        f"<Items>{items}</Items></Root>"
    )
    xml_bytes = b"\xef\xbb\xbf" + text.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"PriceFull{CHAIN_ID}-{ONLINE_STORE}-202609070518.xml", xml_bytes)
    return buf.getvalue()


def _listing_rows(*, include_online_store: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"fname": "Stores7290058140886-000-20260907-050500.xml", "time": "2026-09-07T02:05:00Z"},
        {
            "fname": f"PriceFull{CHAIN_ID}-{SUBCHAIN_ID}-{GOOD_STORE}-20260907-113823.gz",
            "time": "2026-09-07T08:38:29Z",
        },
    ]
    if include_online_store:
        rows.append(
            {
                "fname": f"pricefull{CHAIN_ID}-{ONLINE_STORE}-202609070518.gz",
                "time": "2026-09-07T02:18:00Z",
            }
        )
    return rows


def _successful_fake_open_factory(*, include_online_store: bool = False) -> object:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/json/dir":
            rows = _listing_rows(include_online_store=include_online_store)
            return _FakeResponse(json.dumps({"aaData": rows}).encode("utf-8"), url=url)
        if url.endswith("Stores7290058140886-000-20260907-050500.xml"):
            return _FakeResponse(_stores_xml_bytes(), url=url)
        if url.endswith(f"PriceFull{CHAIN_ID}-{SUBCHAIN_ID}-{GOOD_STORE}-20260907-113823.gz"):
            return _FakeResponse(_pricefull_xml_bytes(GOOD_STORE), url=url)
        if include_online_store and url.endswith(
            f"pricefull{CHAIN_ID}-{ONLINE_STORE}-202609070518.gz"
        ):
            return _FakeResponse(_pricefull_online_xml_bytes(), url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_open


# --- Run-level failures ------------------------------------------------


def test_run_phase1a_login_failure_is_run_level(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(b"<html>no csrf token</html>", url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    stores, pricefull_by_store, summary = run.run_phase1a([GOOD_STORE], base_url=BASE_URL)

    assert stores == []
    assert pricefull_by_store == {}
    assert summary.session_established is False
    assert summary.outcomes == []
    assert summary.run_level_failure_reason is not None
    assert "login" in summary.run_level_failure_reason


def test_run_phase1a_listing_failure_is_run_level(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/json/dir":
            return _FakeResponse(b"not json", url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    stores, pricefull_by_store, summary = run.run_phase1a([GOOD_STORE], base_url=BASE_URL)

    assert stores == []
    assert pricefull_by_store == {}
    assert summary.session_established is True
    assert summary.outcomes == []
    assert summary.run_level_failure_reason is not None
    assert "listing" in summary.run_level_failure_reason


# --- End-to-end success and isolation -----------------------------------


def test_run_phase1a_succeeds_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _successful_fake_open_factory())

    stores, pricefull_by_store, summary = run.run_phase1a([GOOD_STORE], base_url=BASE_URL)

    assert len(stores) == 1
    assert stores[0].store_id == GOOD_STORE
    assert GOOD_STORE in pricefull_by_store
    assert len(pricefull_by_store[GOOD_STORE]) == 5
    assert summary.run_level_failure_reason is None
    assert summary.succeeded_count == 2  # stores + pricefull
    assert summary.failed_count == 0


def test_run_phase1a_one_pricefull_failure_does_not_block_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _successful_fake_open_factory())

    stores, pricefull_by_store, summary = run.run_phase1a(
        [GOOD_STORE, MISSING_STORE], base_url=BASE_URL
    )

    assert GOOD_STORE in pricefull_by_store
    assert MISSING_STORE not in pricefull_by_store

    pricefull_outcomes = {
        outcome.store_id: outcome
        for outcome in summary.outcomes
        if outcome.file_kind == "pricefull"
    }
    assert pricefull_outcomes[GOOD_STORE].succeeded is True
    assert pricefull_outcomes[MISSING_STORE].succeeded is False
    assert pricefull_outcomes[MISSING_STORE].failed_stage == "discovery"
    assert pricefull_outcomes[MISSING_STORE].error_type == "DiscoveryError"

    # Stores must still have succeeded regardless of the unrelated failure.
    stores_outcome = next(o for o in summary.outcomes if o.file_kind == "stores")
    assert stores_outcome.succeeded is True
    assert len(stores) == 1


def test_run_phase1a_both_schema_families_succeed_in_one_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standard-family store and the online/ZIP/alternate-schema store
    can both succeed within the same run, each yielding its own correct
    raw dataclass family."""
    monkeypatch.setattr(
        urllib.request.OpenerDirector,
        "open",
        _successful_fake_open_factory(include_online_store=True),
    )

    stores, pricefull_by_store, summary = run.run_phase1a(
        [GOOD_STORE, ONLINE_STORE], base_url=BASE_URL
    )

    assert GOOD_STORE in pricefull_by_store
    assert ONLINE_STORE in pricefull_by_store

    standard_items = pricefull_by_store[GOOD_STORE]
    online_items = pricefull_by_store[ONLINE_STORE]
    assert all(isinstance(item, RamiLevyPriceItemRawStandard) for item in standard_items)
    assert all(isinstance(item, RamiLevyPriceItemRawOnline) for item in online_items)

    pricefull_outcomes = {
        outcome.store_id: outcome
        for outcome in summary.outcomes
        if outcome.file_kind == "pricefull"
    }
    assert pricefull_outcomes[GOOD_STORE].succeeded is True
    assert pricefull_outcomes[GOOD_STORE].schema_family == "standard"
    assert pricefull_outcomes[ONLINE_STORE].succeeded is True
    assert pricefull_outcomes[ONLINE_STORE].schema_family == "online"

    # Both raw representations of the online store's ID are preserved
    # unchanged, even though validation treated them as equivalent.
    online_item = online_items[0]
    assert isinstance(online_item, RamiLevyPriceItemRawOnline)
    assert online_item.store_id == ONLINE_STORE_XML_UNPADDED
    assert pricefull_outcomes[ONLINE_STORE].filename_ids["store_id"] == ONLINE_STORE
    assert pricefull_outcomes[ONLINE_STORE].xml_ids["store_id"] == ONLINE_STORE_XML_UNPADDED
    assert pricefull_outcomes[ONLINE_STORE].ids_matched is True

    assert len(stores) == 1


def test_run_phase1a_run_summary_has_no_embedded_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _successful_fake_open_factory())

    _, _, summary = run.run_phase1a([GOOD_STORE], base_url=BASE_URL)

    for outcome in summary.outcomes:
        assert not hasattr(outcome, "items")
        assert not hasattr(outcome, "stores")


# --- Live tests against the real provider (opt-in only) --------------------

_LIVE_TESTS_ENABLED = os.environ.get("SMARTCART_LIVE_RAMI_LEVY_TESTS") == "1"
_SKIP_LIVE_REASON = (
    "Live Rami Levy network tests are opt-in; set "
    "SMARTCART_LIVE_RAMI_LEVY_TESTS=1 to run them against the real provider."
)


_STANDARD_ITEM_FIELDS = {
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
_ONLINE_ITEM_FIELDS = {
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


@pytest.mark.skipif(not _LIVE_TESTS_ENABLED, reason=_SKIP_LIVE_REASON)
def test_live_login_listing_stores_and_both_pricefull_families() -> None:
    """Bounded live acceptance: login, root listing, current Stores, one
    representative standard-family store, and StoreID 039 (online/
    alternate family) all through the real provider, normal TLS only."""
    import dataclasses

    representative_store = "001"  # any ordinary store; zero-padded per observed convention
    stores, pricefull_by_store, summary = run.run_phase1a([representative_store, ONLINE_STORE])

    assert summary.run_level_failure_reason is None
    assert summary.session_established is True

    # Observed live around 99 stores at reconnaissance time -- checked as a
    # sanity range, never hardcoded as a permanent contract.
    assert len(stores) > 0

    stores_outcome = next(o for o in summary.outcomes if o.file_kind == "stores")
    assert stores_outcome.succeeded is True

    standard_outcome = next(
        o
        for o in summary.outcomes
        if o.file_kind == "pricefull" and o.store_id == representative_store
    )
    assert standard_outcome.succeeded is True
    assert standard_outcome.schema_family == "standard"
    assert standard_outcome.ids_matched is True

    online_outcome = next(
        o for o in summary.outcomes if o.file_kind == "pricefull" and o.store_id == ONLINE_STORE
    )
    assert online_outcome.succeeded is True
    assert online_outcome.schema_family == "online"
    assert online_outcome.ids_matched is True
    # The one evidence-backed equivalence: catalog/filename "039" vs.
    # XML-carried "39", both preserved, never mutated into each other.
    assert online_outcome.filename_ids["store_id"] == ONLINE_STORE
    assert online_outcome.xml_ids["store_id"] == ONLINE_STORE_XML_UNPADDED

    assert representative_store in pricefull_by_store
    assert ONLINE_STORE in pricefull_by_store

    standard_item = pricefull_by_store[representative_store][0]
    assert isinstance(standard_item, RamiLevyPriceItemRawStandard)
    standard_field_names = {f.name for f in dataclasses.fields(standard_item)}
    assert standard_field_names == _STANDARD_ITEM_FIELDS

    online_item = pricefull_by_store[ONLINE_STORE][0]
    assert isinstance(online_item, RamiLevyPriceItemRawOnline)
    assert online_item.store_id == ONLINE_STORE_XML_UNPADDED
    online_field_names = {f.name for f in dataclasses.fields(online_item)}
    assert online_field_names == _ONLINE_ITEM_FIELDS
    assert "last_sale_date_time" not in online_field_names
