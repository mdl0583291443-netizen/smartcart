"""Discovery of the current Rami Levy Stores/PriceFull files from an
already-fetched directory listing.

This module is deliberately pure/offline: it takes the rows already
returned by `RamiLevySession.list_directory()` (see session.py for the
network call and authentication) and decides which row is the current
Stores file, or the current PriceFull file for a given store_id. It never
makes a network call itself.

Filenames are discovery metadata/hints only -- never treated as the source
of truth for chain/subchain/store identity (see validate.py for the
authoritative cross-check against XML-derived IDs). Reconnaissance
observed exactly two real filename shapes for PriceFull files, both
supported explicitly here (not guessed):

- "standard": PriceFull<chain>-<subchain>-<store>-<date8>-<time6>.gz
  used by ordinary numbered stores, e.g.
  PriceFull7290058140886-001-001-20260907-001018.gz
- "compact": pricefull<chain>-<store>-<timestamp12>.gz (lowercase, no
  subchain segment), observed specifically for store 039 (the online
  store), e.g. pricefull7290058140886-039-202609070518.gz

If a requested store_id cannot be confidently matched by either known
shape, this raises DiscoveryError rather than guessing via substring
matching -- that may mean the store genuinely has no PriceFull file
listed, or it may mean the filename format has drifted into a third,
not-yet-observed shape; this module does not attempt to distinguish those
two cases without further evidence.

IMPORTANT: filename shape is recorded on DiscoveredFile purely as
observational metadata/hint (see parse.py's docstring). It is never used
to decide the XML schema family -- that decision belongs entirely to
parse.py, based on the actual parsed content. In particular, this module
does not special-case store_id "039" or any other value.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

_STORES_RE = re.compile(r"^Stores(?P<chain_id>\d+)-\d+-\d{8}-\d{6}\.xml$", re.IGNORECASE)

_PRICEFULL_STANDARD_RE = re.compile(
    r"^pricefull(?P<chain_id>\d+)-(?P<subchain_id>\d+)-(?P<store_id>\d+)-\d{8}-\d{6}\.gz$",
    re.IGNORECASE,
)
_PRICEFULL_COMPACT_RE = re.compile(
    r"^pricefull(?P<chain_id>\d+)-(?P<store_id>\d+)-\d{12}\.gz$",
    re.IGNORECASE,
)


class DiscoveryError(Exception):
    """Raised when a current Stores/PriceFull candidate cannot be found or
    confidently identified among the listing rows."""


@dataclass(frozen=True)
class DiscoveredFile:
    """One discovered file: its exact listing filename plus the listing's
    own timestamp for it. Contains no downloaded bytes.

    `filename_shape` ("standard" | "compact" | None) is which known
    PriceFull filename shape matched (None for Stores). It is recorded
    purely as observational metadata -- see module docstring -- and is
    never used to decide the XML schema family.
    """

    filename: str
    listing_time_raw: str
    filename_shape: str | None = None


def _row_filename(row: object) -> str | None:
    if not isinstance(row, dict):
        return None
    fname = row.get("fname")
    return fname if isinstance(fname, str) else None


def _row_time(row: object) -> str:
    if not isinstance(row, dict):
        return ""
    time_value = row.get("time")
    return time_value if isinstance(time_value, str) else ""


def _latest(candidates: list[tuple[object, str | None]]) -> DiscoveredFile:
    latest_row, shape = max(candidates, key=lambda pair: _row_time(pair[0]))
    return DiscoveredFile(
        filename=_row_filename(latest_row) or "",
        listing_time_raw=_row_time(latest_row),
        filename_shape=shape,
    )


def find_stores_file(rows: Sequence[object]) -> DiscoveredFile:
    """Find the current Stores file among already-fetched listing rows."""
    candidates: list[tuple[object, str | None]] = [
        (row, None) for row in rows if (fname := _row_filename(row)) and _STORES_RE.match(fname)
    ]
    if not candidates:
        raise DiscoveryError("No Stores file found matching the known filename pattern.")
    return _latest(candidates)


def find_pricefull_file(rows: Sequence[object], store_id: str) -> DiscoveredFile:
    """Find the current PriceFull file for one store_id among
    already-fetched listing rows.

    store_id must be passed exactly as the chain represents it (e.g.
    "039", not "39") -- zero-padding is preserved exactly and never
    inferred.
    """
    candidates: list[tuple[object, str | None]] = []
    for row in rows:
        fname = _row_filename(row)
        if fname is None:
            continue
        match = _PRICEFULL_STANDARD_RE.match(fname)
        if match is not None and match.group("store_id") == store_id:
            candidates.append((row, "standard"))
            continue
        match = _PRICEFULL_COMPACT_RE.match(fname)
        if match is not None and match.group("store_id") == store_id:
            candidates.append((row, "compact"))

    if not candidates:
        raise DiscoveryError(
            f"No PriceFull file found for store_id={store_id!r} matching either known "
            "filename shape (standard or compact). This may mean the store has no "
            "PriceFull file currently listed, or it may indicate unrecognized "
            "filename-format drift -- these two cases are not distinguished here."
        )
    return _latest(candidates)
