"""Integration tests for smartcart.collectors.shufersal.run.

Two clearly separate parts:

1. Offline tests (run by default, no network access) that patch
   `urllib.request.urlopen` with deterministic fake responses to exercise
   run.py's orchestration: end-to-end success, stale-signed-URL
   rediscovery, network failure, empty body, and one PriceFull failure not
   blocking other stores.

2. Live tests against the real Shufersal portal, skipped by default. They
   only run when SMARTCART_LIVE_SHUFERSAL_TESTS=1 is set, so normal CI
   never fails because the live retailer endpoint is unavailable.
"""

from __future__ import annotations

import gzip
import os
import urllib.error
import urllib.request

import pytest

from smartcart.collectors.shufersal import discovery, download, run

GOOD_STORE = "413"
BAD_STORE = "999"
CHAIN_ID = "7290027600007"
SUBCHAIN_ID = "002"


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _pricefull_xml(store_id: str, n_items: int = 12) -> bytes:
    items = "".join(
        "<Item>"
        "<PriceUpdateTime>2026-09-04T06:23:00</PriceUpdateTime>"
        f"<ItemCode>{1000000000000 + i}</ItemCode>"
        "<LastSaleDateTime>2026-09-04T00:00:00</LastSaleDateTime>"
        "<ItemType>1</ItemType>"
        f"<ItemName>Test Item {i}</ItemName>"
        "<ManufactureName>Acme</ManufactureName>"
        "<ManufactureCountry>IL</ManufactureCountry>"
        f"<ManufactureItemDescription>Test Item {i}</ManufactureItemDescription>"
        "<UnitQty>Gram</UnitQty>"
        "<Quantity>100.00</Quantity>"
        "<UnitOfMeasure>100 Gram</UnitOfMeasure>"
        "<bIsWeighted>0</bIsWeighted>"
        "<QtyInPackage>1</QtyInPackage>"
        "<ItemPrice>10.00</ItemPrice>"
        "<UnitOfMeasurePrice>10.00</UnitOfMeasurePrice>"
        "<AllowDiscount>1</AllowDiscount>"
        "<ItemStatus />"
        "</Item>"
        for i in range(n_items)
    )
    xml = (
        f"<Root><ChainID>{CHAIN_ID}</ChainID><SubChainID>{SUBCHAIN_ID}</SubChainID>"
        f"<StoreID>{store_id}</StoreID><BikoretNo>0</BikoretNo><Items>{items}</Items></Root>"
    )
    return b"\xef\xbb\xbf" + xml.encode("utf-8")


def _stores_xml() -> bytes:
    xml = (
        f"<Chain><ChainID>{CHAIN_ID}</ChainID><ChainName>Test Chain</ChainName>"
        "<LastUpdateDate>2026-09-07</LastUpdateDate><LastUpdateTime>02:01:01</LastUpdateTime>"
        f"<SubChains><SubChain><SubChainID>{SUBCHAIN_ID}</SubChainID>"
        "<SubChainName>Test Sub</SubChainName>"
        f"<Stores><Store><StoreID>{GOOD_STORE}</StoreID><BikoretNo>7</BikoretNo>"
        "<StoreType>1</StoreType>"
        "<StoreName>Test Store</StoreName><Address>Test Address</Address><City>2530</City>"
        "<ZIPCode>7030336</ZIPCode></Store></Stores></SubChain></SubChains></Chain>"
    )
    return b"\xef\xbb\xbf" + xml.encode("utf-8")


def _pricefull_listing_html(store_id: str) -> str:
    return (
        "<table><tbody><tr>"
        f'<td><a href="https://fake.blob.example/pricefull/PriceFull{CHAIN_ID}-{SUBCHAIN_ID}-'
        f'{store_id}-20260907-034000.gz?sv=x&amp;se=2026-09-07T09%3A00%3A00Z&amp;sp=r">Download</a></td>'
        "<td>9/7/2026 3:40:00 AM</td>"
        "</tr></tbody></table>"
    )


def _stores_listing_html() -> str:
    return (
        "<table><tbody><tr>"
        f'<td><a href="https://fake.blob.example/stores/Stores{CHAIN_ID}-000-20260907-020.gz'
        '?sv=x&amp;se=2026-09-07T09%3A00%3A00Z&amp;sp=r">Download</a></td>'
        "<td>9/7/2026 12:20:00 AM</td>"
        "</tr></tbody></table>"
    )


def _empty_listing_html() -> str:
    return "<table><tbody></tbody></table>"


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep offline tests fast/deterministic regardless of retry backoff."""
    monkeypatch.setattr(discovery, "_DISCOVERY_RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(download, "_DOWNLOAD_RETRY_BACKOFF_SECONDS", 0.0)


# --- Offline discovery tests (run in normal CI, no network) --------------


def test_discover_pricefull_file_unescapes_html_entities_in_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: the portal HTML-escapes '&' as '&amp;' inside the
    href attribute. If that is not unescaped, the signed URL's query
    string (sig/se/etc.) is corrupted and the blob store 404s -- this was
    caught only by the live acceptance run, not by mocked tests that only
    checked for substrings, so it is locked in here explicitly."""

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    discovered = discovery.discover_pricefull_file(GOOD_STORE)

    assert "&amp;" not in discovered.url
    assert "?sv=" in discovered.url
    assert "&se=" in discovered.url
    assert "&sp=" in discovered.url


# --- Offline orchestration tests (run in normal CI, no network) -----------


def test_run_stores_and_pricefull_succeed_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=5" in url:
            return _FakeResponse(_stores_listing_html().encode("utf-8"))
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        if "/stores/" in url:
            return _FakeResponse(gzip.compress(_stores_xml()))
        return _FakeResponse(gzip.compress(_pricefull_xml(GOOD_STORE)))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    stores, stores_outcome = run.run_stores()
    assert stores_outcome.succeeded
    assert len(stores) == 1
    assert stores_outcome.record_count == 1

    items, item_outcome = run.run_pricefull_for_store(GOOD_STORE)
    assert item_outcome.succeeded
    assert len(items) == 12
    assert item_outcome.ids_matched is True


def test_run_pricefull_rediscovers_once_on_expired_signed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_attempts = {"count": 0}
    listing_attempts = {"count": 0}

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            listing_attempts["count"] += 1
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        download_attempts["count"] += 1
        if download_attempts["count"] == 1:
            raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)  # type: ignore[arg-type]
        return _FakeResponse(gzip.compress(_pricefull_xml(GOOD_STORE)))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert outcome.succeeded
    assert len(items) == 12
    # Expired once (stale URL), then exactly one fresh attempt -- never a
    # repeated retry of the same stale signed URL.
    assert download_attempts["count"] == 2
    assert listing_attempts["count"] == 2


def test_run_pricefull_gives_up_after_one_rediscovery_if_still_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        raise urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "download"
    assert outcome.error_type == "DownloadAuthExpiredError"


def test_run_pricefull_network_failure_is_recorded_as_download_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "download"
    assert outcome.error_type == "DownloadNetworkError"


def test_run_pricefull_empty_body_is_recorded_as_download_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        return _FakeResponse(b"")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "download"
    assert outcome.error_type == "DownloadEmptyBodyError"


def test_run_pricefull_discovery_failure_when_no_files_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        return _FakeResponse(_empty_listing_html().encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(BAD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "discovery"


def test_run_pricefull_persistent_5xx_is_recorded_as_download_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", hdrs=None, fp=None)  # type: ignore[arg-type]

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "download"
    assert outcome.error_type == "DownloadNetworkError"


def test_run_pricefull_discovery_exhausts_retries_on_persistent_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        raise urllib.error.URLError("dns resolution failed")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "discovery"
    assert outcome.error_type == "DiscoveryError"


def test_run_pricefull_corrupt_gzip_is_recorded_as_transport_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        good = gzip.compress(_pricefull_xml(GOOD_STORE))
        return _FakeResponse(good[: len(good) // 2])  # truncated -> corrupt gzip

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "transport"
    assert outcome.error_type == "TransportError"


def test_run_pricefull_malformed_xml_is_recorded_as_parse_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        return _FakeResponse(gzip.compress(b"<Root><Unclosed>"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    items, outcome = run.run_pricefull_for_store(GOOD_STORE)

    assert items == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "parse"
    assert outcome.error_type == "ParseError"


def test_run_stores_malformed_xml_is_recorded_as_parse_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=5" in url:
            return _FakeResponse(_stores_listing_html().encode("utf-8"))
        return _FakeResponse(gzip.compress(b"<Chain><Unclosed>"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    stores, outcome = run.run_stores()

    assert stores == []
    assert not outcome.succeeded
    assert outcome.failed_stage == "parse"
    assert outcome.error_type == "ParseError"


def test_run_phase1a_stores_failure_is_recorded_and_does_not_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Stores-stage failure is foundational (unlike an isolated PriceFull
    failure): this proves run_phase1a still (1) represents the failure in
    the run summary, (2) does not let it escape as an uncaught exception,
    and (3) does not silently report/return as though Stores succeeded."""

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=5" in url:
            return _FakeResponse(_empty_listing_html().encode("utf-8"))  # Stores discovery fails
        if "catID=2" in url:
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        return _FakeResponse(gzip.compress(_pricefull_xml(GOOD_STORE)))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    stores, pricefull_by_store, summary = run.run_phase1a([GOOD_STORE])

    # (3) Not silently treated as success: no fabricated Stores payload.
    assert stores == []

    # (1) Represented in the run outcome/summary.
    stores_outcomes = [outcome for outcome in summary.outcomes if outcome.file_kind == "stores"]
    assert len(stores_outcomes) == 1
    assert stores_outcomes[0].succeeded is False
    assert stores_outcomes[0].failed_stage == "discovery"
    assert stores_outcomes[0].error_type == "DiscoveryError"

    # (2) Did not escape as an uncaught exception: run_phase1a returned
    # normally and the rest of the run (unrelated PriceFull processing)
    # still completed.
    assert GOOD_STORE in pricefull_by_store
    assert summary.failed_count == 1
    assert summary.succeeded_count == 1


def test_run_phase1a_one_pricefull_failure_does_not_block_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        url = request.full_url
        if "catID=5" in url:
            return _FakeResponse(_stores_listing_html().encode("utf-8"))
        if "catID=2" in url:
            if f"storeId={BAD_STORE}" in url:
                return _FakeResponse(_empty_listing_html().encode("utf-8"))
            return _FakeResponse(_pricefull_listing_html(GOOD_STORE).encode("utf-8"))
        if "/stores/" in url:
            return _FakeResponse(gzip.compress(_stores_xml()))
        return _FakeResponse(gzip.compress(_pricefull_xml(GOOD_STORE)))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    stores, pricefull_by_store, summary = run.run_phase1a([GOOD_STORE, BAD_STORE])

    assert len(stores) == 1
    assert GOOD_STORE in pricefull_by_store
    assert BAD_STORE not in pricefull_by_store

    outcomes_by_store = {
        outcome.store_id: outcome
        for outcome in summary.outcomes
        if outcome.file_kind == "pricefull"
    }
    assert outcomes_by_store[BAD_STORE].succeeded is False
    assert outcomes_by_store[BAD_STORE].failed_stage == "discovery"
    assert outcomes_by_store[GOOD_STORE].succeeded is True

    assert summary.succeeded_count == 2  # stores + good pricefull
    assert summary.failed_count == 1

    # RunSummary must never embed the (potentially huge) parsed payload.
    for outcome in summary.outcomes:
        assert not hasattr(outcome, "items")
        assert not hasattr(outcome, "stores")


# --- Live tests against the real Shufersal portal (opt-in only) -----------

_LIVE_TESTS_ENABLED = os.environ.get("SMARTCART_LIVE_SHUFERSAL_TESTS") == "1"
_SKIP_LIVE_REASON = (
    "Live Shufersal network tests are opt-in; set "
    "SMARTCART_LIVE_SHUFERSAL_TESTS=1 to run them against the real portal."
)


@pytest.mark.skipif(not _LIVE_TESTS_ENABLED, reason=_SKIP_LIVE_REASON)
def test_live_discover_and_process_current_stores_file() -> None:
    stores, outcome = run.run_stores()
    assert outcome.succeeded
    assert len(stores) > 0


@pytest.mark.skipif(not _LIVE_TESTS_ENABLED, reason=_SKIP_LIVE_REASON)
def test_live_discover_and_process_pricefull_for_a_known_store() -> None:
    items, outcome = run.run_pricefull_for_store("1")
    assert outcome.succeeded
    assert len(items) > 0
