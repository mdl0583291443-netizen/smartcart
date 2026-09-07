"""Gzip transport verification/decompression for Shufersal files.

Stores and PriceFull downloads were both observed gzip-compressed in
reconnaissance and in live runs, so this decompression logic is shared
between them -- but that observation is not treated as a permanent source
contract here: this module never assumes a file *should* be gzip based on
its type. It verifies compression from content/magic bytes only -- never a
filename extension, and never a hardcoded "Stores/PriceFull is gzip" rule
-- and decompresses whatever is actually gzip-shaped. It knows nothing
about XML or Shufersal's record schema (see parse.py); in particular it
does not touch text encoding or a leading BOM, which are parse.py's
concern once the bytes are decompressed.
"""

from __future__ import annotations

import gzip
import zlib

_GZIP_MAGIC = b"\x1f\x8b"


class TransportError(Exception):
    """Raised when input bytes are not valid gzip, or decompression fails."""


def is_gzip(data: bytes) -> bool:
    """Check for gzip magic bytes. Never relies on a filename extension."""
    return data[:2] == _GZIP_MAGIC


def decompress(data: bytes) -> bytes:
    """Verify gzip magic bytes and decompress.

    Raises TransportError if the input does not start with gzip magic
    bytes, or if decompression fails partway through (corrupt gzip).
    Never falls back to treating non-gzip or corrupt-gzip bytes as plain
    XML -- a transport failure must surface as a transport failure.
    """
    if not is_gzip(data):
        raise TransportError(
            f"Input does not start with gzip magic bytes (got {data[:2]!r}); "
            "refusing to decompress or fall back to plain-text parsing."
        )
    try:
        return gzip.decompress(data)
    except (OSError, EOFError, zlib.error) as exc:
        raise TransportError(f"Corrupt gzip data: {exc}") from exc
