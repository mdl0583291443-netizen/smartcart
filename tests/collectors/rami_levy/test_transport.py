"""Tests for smartcart.collectors.rami_levy.transport.

All deterministic, no network access.
"""

from __future__ import annotations

import gzip
import io
import zipfile

import pytest

from smartcart.collectors.rami_levy import transport
from smartcart.collectors.rami_levy.transport import TransportError, is_gzip, is_zip, normalize


def _single_member_zip(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, content)
    return buf.getvalue()


def test_is_gzip_true_for_real_gzip_bytes() -> None:
    assert is_gzip(gzip.compress(b"<Root></Root>")) is True


def test_is_gzip_false_for_plain_xml_bytes() -> None:
    assert is_gzip(b"<Root></Root>") is False


def test_normalize_decompresses_gzip_input() -> None:
    original = b"<Root><ChainID>1</ChainID></Root>"
    assert normalize(gzip.compress(original)) == original


def test_normalize_passes_through_non_gzip_bytes_unchanged() -> None:
    """PriceFull arriving as plain (non-gzip) XML must not fail merely
    because the category is normally gzip -- transport is content-aware."""
    plain_xml = b"<Root><ChainID>1</ChainID></Root>"
    assert normalize(plain_xml) == plain_xml


def test_normalize_passes_through_utf16_bom_bytes_unchanged_when_not_gzip() -> None:
    """Stores arrives as plain UTF-16 LE XML with a BOM; transport must
    not attempt to touch encoding at all, just pass it through."""
    utf16_bytes = b"\xff\xfe" + "<Root><ChainID>1</ChainID></Root>".encode("utf-16-le")
    assert normalize(utf16_bytes) == utf16_bytes


def test_normalize_rejects_corrupt_gzip() -> None:
    payload = gzip.compress(b"hello world" * 1000)
    truncated = payload[: len(payload) // 2]
    assert is_gzip(truncated) is True
    with pytest.raises(TransportError):
        normalize(truncated)


def test_normalize_empty_bytes_pass_through_unchanged() -> None:
    """Empty bytes are not gzip-shaped, so transport itself does not fail
    on them -- an empty body is a download-stage concern (see
    download.py), and empty content will fail at parse-stage regardless."""
    assert normalize(b"") == b""


# --- ZIP (the "online" PriceFull family's actual container) --------------


def test_is_zip_true_for_real_zip_bytes() -> None:
    assert is_zip(_single_member_zip("PriceFull.xml", b"<Root></Root>")) is True


def test_is_zip_false_for_gzip_bytes() -> None:
    assert is_zip(gzip.compress(b"<Root></Root>")) is False


def test_normalize_extracts_single_zip_member() -> None:
    original = b"<Root><ChainId>7290058140886</ChainId></Root>"
    zip_bytes = _single_member_zip("PriceFull7290058140886-039-202609070518.xml", original)
    assert normalize(zip_bytes) == original


def test_normalize_rejects_empty_zip_archive() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w"):
        pass  # zero members
    with pytest.raises(TransportError):
        normalize(buf.getvalue())


def test_normalize_rejects_multi_member_zip_archive() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PriceFull.xml", b"<Root></Root>")
        zf.writestr("extra.txt", b"unexpected second member")
    with pytest.raises(TransportError):
        normalize(buf.getvalue())


def test_normalize_rejects_malformed_zip() -> None:
    # Correct ZIP magic bytes, but truncated/corrupt central directory.
    corrupt = b"PK\x03\x04" + b"\x00" * 50
    assert is_zip(corrupt) is True
    with pytest.raises(TransportError):
        normalize(corrupt)


def test_normalize_rejects_zip_exceeding_declared_size_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The member's declared (central-directory) uncompressed size is
    checked before decompressing -- a small, fast ceiling here proves the
    same code path that guards the real 100 MB ceiling, without needing a
    multi-hundred-megabyte fixture."""
    monkeypatch.setattr(transport, "MAX_ZIP_UNCOMPRESSED_BYTES", 10)
    zip_bytes = _single_member_zip("PriceFull.xml", b"<Root>" + b"x" * 100 + b"</Root>")
    with pytest.raises(TransportError):
        normalize(zip_bytes)


def test_normalize_accepts_zip_within_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "MAX_ZIP_UNCOMPRESSED_BYTES", 10_000)
    original = b"<Root><ChainId>1</ChainId></Root>"
    zip_bytes = _single_member_zip("PriceFull.xml", original)
    assert normalize(zip_bytes) == original


def test_normalize_actual_size_ceiling_also_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defense in depth: even if the declared size were smaller than the
    real decompressed size, the actual extracted length is checked too.
    A legitimately-written ZIP always has declared == actual size, so this
    exercises the same rejection outcome as the declared-size check above
    -- both guards are in place, not just one."""
    monkeypatch.setattr(transport, "MAX_ZIP_UNCOMPRESSED_BYTES", 5)
    zip_bytes = _single_member_zip("PriceFull.xml", b"0123456789")
    with pytest.raises(TransportError):
        normalize(zip_bytes)
