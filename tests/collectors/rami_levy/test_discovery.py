"""Tests for smartcart.collectors.rami_levy.discovery.

Pure/offline: discovery.py takes already-fetched listing rows and never
makes a network call, so these tests just construct row dicts directly.
"""

from __future__ import annotations

import pytest

from smartcart.collectors.rami_levy.discovery import (
    DiscoveryError,
    find_pricefull_file,
    find_stores_file,
)


def _row(fname: str, time: str) -> dict[str, object]:
    return {"fname": fname, "time": time}


# --- Stores ------------------------------------------------------------


def test_find_stores_file_picks_latest_by_time() -> None:
    rows = [
        _row("Stores7290058140886-000-20260905-050500.xml", "2026-09-05T02:05:00Z"),
        _row("Stores7290058140886-000-20260907-050500.xml", "2026-09-07T02:05:00Z"),
        _row("Stores7290058140886-000-20260906-050500.xml", "2026-09-06T02:05:00Z"),
    ]
    result = find_stores_file(rows)
    assert result.filename == "Stores7290058140886-000-20260907-050500.xml"
    assert result.listing_time_raw == "2026-09-07T02:05:00Z"


def test_find_stores_file_ignores_non_stores_rows() -> None:
    rows = [
        _row("PriceFull7290058140886-001-001-20260907-001018.gz", "2026-09-07T00:10:18Z"),
        _row("Stores7290058140886-000-20260907-050500.xml", "2026-09-07T02:05:00Z"),
    ]
    result = find_stores_file(rows)
    assert result.filename == "Stores7290058140886-000-20260907-050500.xml"


def test_find_stores_file_raises_when_none_found() -> None:
    with pytest.raises(DiscoveryError):
        find_stores_file([_row("PriceFull7290058140886-001-001-20260907-001018.gz", "t")])


# --- PriceFull: standard shape ------------------------------------------


def test_find_pricefull_file_standard_shape_matches_exact_store_id() -> None:
    rows = [
        _row("PriceFull7290058140886-001-001-20260907-001018.gz", "2026-09-07T00:10:18Z"),
        _row("PriceFull7290058140886-001-002-20260907-001010.gz", "2026-09-07T00:10:10Z"),
    ]
    result = find_pricefull_file(rows, "001")
    assert result.filename == "PriceFull7290058140886-001-001-20260907-001018.gz"


def test_find_pricefull_file_picks_latest_among_multiple_for_same_store() -> None:
    rows = [
        _row("PriceFull7290058140886-001-003-20260907-001017.gz", "2026-09-07T00:10:17Z"),
        _row("PriceFull7290058140886-001-003-20260907-060016.gz", "2026-09-07T03:00:16Z"),
    ]
    result = find_pricefull_file(rows, "003")
    assert result.filename == "PriceFull7290058140886-001-003-20260907-060016.gz"


def test_find_pricefull_file_zero_padding_is_exact_not_substring() -> None:
    """'039' is not the same discovery token as '39' -- and must not be
    matched via substring search against a filename that merely contains
    the digits '39' somewhere (e.g. in a timestamp)."""
    rows = [
        _row("PriceFull7290058140886-001-039-20260907-001039.gz", "2026-09-07T00:10:39Z"),
        _row("PriceFull7290058140886-001-139-20260907-001018.gz", "2026-09-07T00:10:18Z"),
    ]
    result = find_pricefull_file(rows, "039")
    assert result.filename == "PriceFull7290058140886-001-039-20260907-001039.gz"

    with pytest.raises(DiscoveryError):
        find_pricefull_file(rows, "39")  # unpadded token must not match "039"


# --- PriceFull: compact/online shape (store 039 in recon) ----------------


def test_find_pricefull_file_compact_shape_matches_online_store() -> None:
    """Reconnaissance found store 039 (the online store) publishes
    PriceFull under a different, lowercase, subchain-less filename shape:
    pricefull<chain>-<store>-<timestamp12>.gz -- this must be recognized,
    not treated as unrecognized drift, since it is a directly observed
    real shape."""
    rows = [
        _row("pricefull7290058140886-039-202609070518.gz", "2026-09-07T02:18:00Z"),
        _row("pricefull7290058140886-039-202609060519.gz", "2026-09-06T02:19:00Z"),
    ]
    result = find_pricefull_file(rows, "039")
    assert result.filename == "pricefull7290058140886-039-202609070518.gz"


def test_find_pricefull_file_does_not_confuse_compact_shape_with_incremental_price() -> None:
    """Incremental (non-Full) 'price' files share a filename prefix with
    'pricefull' as a literal string, but are a different token/category
    entirely and must never be matched."""
    rows = [
        _row("price7290058140886-039-202607150900.gz", "2026-07-15T06:04:49Z"),
        _row("pricefull7290058140886-039-202609070518.gz", "2026-09-07T02:18:00Z"),
    ]
    result = find_pricefull_file(rows, "039")
    assert result.filename == "pricefull7290058140886-039-202609070518.gz"


def test_find_pricefull_file_case_insensitive_prefix() -> None:
    """Reconnaissance observed both 'PriceFull' and 'pricefull' casing
    across the live listing; both must be recognized."""
    rows = [_row("PRICEFULL7290058140886-001-001-20260907-001018.gz", "2026-09-07T00:10:18Z")]
    result = find_pricefull_file(rows, "001")
    assert result.filename == "PRICEFULL7290058140886-001-001-20260907-001018.gz"


# --- Source drift: neither known shape matches ---------------------------


def test_find_pricefull_file_reports_discovery_error_not_a_guess_on_unrecognized_shape() -> None:
    """A filename that starts with 'pricefull' but fits neither known
    shape must not be guessed at via substring matching -- it is simply
    not a candidate, and if no other row matches, this is reported as a
    DiscoveryError (source drift or genuine absence; not distinguished)."""
    rows = [_row("pricefull7290058140886_039_unexpected_format.gz", "2026-09-07T00:00:00Z")]
    with pytest.raises(DiscoveryError):
        find_pricefull_file(rows, "039")


def test_find_pricefull_file_raises_when_store_not_present_at_all() -> None:
    rows = [_row("PriceFull7290058140886-001-001-20260907-001018.gz", "2026-09-07T00:10:18Z")]
    with pytest.raises(DiscoveryError):
        find_pricefull_file(rows, "999")


# --- filename_shape is metadata only, never a schema decision --------------


def test_find_pricefull_file_records_filename_shape_as_metadata() -> None:
    """filename_shape is recorded for observability but discovery.py makes
    no claim about XML schema -- that is parse.py's job, from content."""
    standard_rows = [
        _row("PriceFull7290058140886-001-001-20260907-001018.gz", "2026-09-07T00:10:18Z")
    ]
    assert find_pricefull_file(standard_rows, "001").filename_shape == "standard"

    compact_rows = [_row("pricefull7290058140886-039-202609070518.gz", "2026-09-07T02:18:00Z")]
    assert find_pricefull_file(compact_rows, "039").filename_shape == "compact"


def test_find_stores_file_filename_shape_is_none() -> None:
    rows = [_row("Stores7290058140886-000-20260907-050500.xml", "2026-09-07T02:05:00Z")]
    assert find_stores_file(rows).filename_shape is None
