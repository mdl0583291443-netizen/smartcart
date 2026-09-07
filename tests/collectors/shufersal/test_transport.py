"""Tests for smartcart.collectors.shufersal.transport.

All deterministic, no network access.
"""

from __future__ import annotations

import gzip

import pytest

from smartcart.collectors.shufersal.transport import TransportError, decompress, is_gzip


def test_is_gzip_true_for_real_gzip_bytes() -> None:
    payload = gzip.compress(b"<Root></Root>")
    assert is_gzip(payload) is True


def test_is_gzip_false_for_plain_xml_bytes() -> None:
    assert is_gzip(b"<Root></Root>") is False


def test_is_gzip_false_for_empty_bytes() -> None:
    assert is_gzip(b"") is False


def test_decompress_valid_gzip_roundtrip() -> None:
    original = b"<Root><ChainID>1</ChainID></Root>"
    compressed = gzip.compress(original)
    assert decompress(compressed) == original


def test_decompress_preserves_leading_bom_untouched() -> None:
    """Transport only decompresses; BOM/encoding handling belongs to
    parse.py, so decompress() must hand the BOM through unmodified."""
    original = b"\xef\xbb\xbf<Root><ChainID>1</ChainID></Root>"
    compressed = gzip.compress(original)
    assert decompress(compressed) == original


def test_decompress_rejects_non_gzip_bytes_without_fallback() -> None:
    with pytest.raises(TransportError):
        decompress(b"<Root></Root>")


def test_decompress_rejects_wrong_binary_bytes() -> None:
    with pytest.raises(TransportError):
        decompress(b"\x00\x01\x02\x03not gzip at all")


def test_decompress_rejects_truncated_corrupt_gzip() -> None:
    payload = gzip.compress(b"hello world" * 1000)
    truncated = payload[: len(payload) // 2]
    # Magic bytes are intact (still gzip-shaped) but the stream is corrupt.
    assert is_gzip(truncated) is True
    with pytest.raises(TransportError):
        decompress(truncated)


def test_decompress_rejects_empty_bytes() -> None:
    with pytest.raises(TransportError):
        decompress(b"")
