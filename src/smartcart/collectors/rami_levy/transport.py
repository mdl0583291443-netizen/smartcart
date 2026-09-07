"""Content-aware transport handling for Rami Levy files.

Reconnaissance observed three container states in practice: plain XML
(Stores, UTF-16 LE with BOM), gzip (the "standard" PriceFull family), and
-- discovered by targeted live-variant recon -- a ZIP archive despite a
".gz" filename extension (the "online" PriceFull family, StoreID 039).
None of these are treated as permanent per-file-type contracts: this
module makes no filename- or store-based assumption about which container
a file should use. It only ever decides from the bytes themselves:

- gzip magic bytes present -> decompress (TransportError on corrupt gzip)
- ZIP magic bytes present -> safely extract the single member in memory
  (see the ZIP safety contract below; TransportError on any violation)
- neither -> pass the bytes through unchanged; parse.py is responsible for
  confirming (or rejecting) that the result is valid XML

Text encoding is deliberately not handled here. `xml.etree.ElementTree`
natively detects a UTF-16 or UTF-8 BOM (or assumes UTF-8 if none is
present, per the XML spec) when parsing raw bytes directly, so parse.py
passes the (possibly decompressed/extracted) bytes straight to it rather
than this module guessing an encoding -- see parse.py.

ZIP safety contract (resource-exhaustion / zip-bomb defense, not a
data-quality check):
- processed entirely in memory (io.BytesIO / zipfile.ZipFile); a member is
  never extracted to a filesystem path
- exactly one archive member is required; an empty or multi-member
  archive is rejected
- a malformed archive is rejected
- the member's declared uncompressed size (from the central directory) is
  checked *before* decompressing, and the actual decompressed size is
  checked again afterwards as defense in depth, both against
  `MAX_ZIP_UNCOMPRESSED_BYTES`

`MAX_ZIP_UNCOMPRESSED_BYTES` is a fixed security ceiling, not a signal
about whether the data "looks right": the largest real uncompressed
PriceFull payload observed across either family in reconnaissance was
~13.1 MB (the online family's own ZIP member, store 039). 100 MB gives
roughly 8x headroom over that observed maximum while still bounding
worst-case memory use to a small, fixed amount -- it says nothing about
what counts as valid data, only about how much this process will ever
attempt to hold in memory for one file.
"""

from __future__ import annotations

import gzip
import io
import zipfile
import zlib

_GZIP_MAGIC = b"\x1f\x8b"
# A non-empty ZIP starts with a local file header (PK\x03\x04). A genuinely
# empty archive has no file header at all -- it consists solely of an
# End-of-Central-Directory record (PK\x05\x06). Both are real, standard ZIP
# magic signatures; checking only the first would mean a 0-member archive
# is never even recognized as ZIP-shaped (it would silently fall through
# to the passthrough branch below instead of being explicitly rejected).
_ZIP_LOCAL_FILE_MAGIC = b"PK\x03\x04"
_ZIP_EMPTY_ARCHIVE_MAGIC = b"PK\x05\x06"

MAX_ZIP_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB; see module docstring


class TransportError(Exception):
    """Raised for a corrupt/oversized/malformed gzip or ZIP container."""


def is_gzip(data: bytes) -> bool:
    """Check for gzip magic bytes. Never relies on a filename extension."""
    return data[:2] == _GZIP_MAGIC


def is_zip(data: bytes) -> bool:
    """Check for ZIP magic bytes (local file header, or the
    end-of-central-directory record a genuinely empty archive starts
    with). Never relies on a filename extension -- this is how the
    "online" PriceFull family was discovered despite its ".gz" name."""
    return data[:4] in (_ZIP_LOCAL_FILE_MAGIC, _ZIP_EMPTY_ARCHIVE_MAGIC)


def _extract_single_zip_member(data: bytes) -> bytes:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise TransportError(f"Malformed ZIP archive: {exc}") from exc

    with zf:
        infos = zf.infolist()
        if not infos:
            raise TransportError("ZIP archive contains no members (expected exactly one).")
        if len(infos) > 1:
            names = [info.filename for info in infos]
            raise TransportError(
                f"ZIP archive contains {len(infos)} members (expected exactly one): {names}."
            )

        info = infos[0]
        if info.file_size > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise TransportError(
                f"ZIP member {info.filename!r} declares {info.file_size} uncompressed bytes, "
                f"exceeding the {MAX_ZIP_UNCOMPRESSED_BYTES}-byte safety ceiling; refusing to "
                "decompress."
            )
        payload = zf.read(info)

    if len(payload) > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise TransportError(
            f"ZIP member {info.filename!r} decompressed to {len(payload)} bytes, exceeding "
            f"the {MAX_ZIP_UNCOMPRESSED_BYTES}-byte safety ceiling despite a smaller declared "
            "size."
        )
    return payload


def normalize(data: bytes) -> bytes:
    """Decompress gzip, safely extract a single-member ZIP, or otherwise
    return the bytes unchanged.

    Never fails merely because a file's name/category implied a particular
    container -- only a genuinely corrupt/malformed/oversized gzip or ZIP
    is an error; anything else is passed through for parse.py to accept or
    reject as XML.
    """
    if is_gzip(data):
        try:
            return gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as exc:
            raise TransportError(f"Corrupt gzip data: {exc}") from exc
    if is_zip(data):
        return _extract_single_zip_member(data)
    return data
