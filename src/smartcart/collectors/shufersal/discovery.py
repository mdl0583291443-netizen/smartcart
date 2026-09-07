"""Discovery of current Shufersal Stores/PriceFull files.

Source: the official public Shufersal price-transparency portal
(https://prices.shufersal.co.il). The listing endpoint and its query
parameters were derived directly from that portal's own public
client-side script, not from any third-party scraper project (see
docs/adr/0003).

Signed download URLs returned by the portal are short-lived. Callers must
download immediately after discovery and must never assume a specific
expiry duration: `DiscoveredFile.signed_url_expiry_raw` is the portal's own
stated expiry value (if present in the URL), passed through unparsed and
uninterpreted -- reconnaissance observed roughly 30 minutes across three
samples, which is not a basis for a hardcoded TTL.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape

PORTAL_BASE_URL = "https://prices.shufersal.co.il"
LIST_ENDPOINT_URL = f"{PORTAL_BASE_URL}/FileObject/UpdateCategory"
USER_AGENT = "SmartCart-Shufersal-Collector/1.0"
# Live acceptance testing observed the listing endpoint itself taking over
# 30s to respond on occasion; 60s gives headroom without waiting forever.
REQUEST_TIMEOUT_SECONDS = 60.0

CATEGORY_STORES = 5
CATEGORY_PRICE_FULL = 2

_DISCOVERY_RETRY_ATTEMPTS = 2
_DISCOVERY_RETRY_BACKOFF_SECONDS = 1.0

# Matches one file row: the download link's href, followed by the listing
# time cell. Deliberately minimal (only the two columns we need) so it is
# not brittle against unrelated column changes elsewhere in the table.
_ROW_PATTERN = re.compile(
    r'<td><a href="(?P<url>[^"]+)"[^>]*>.*?</a></td>\s*<td>(?P<time>[^<]+)</td>',
    re.DOTALL,
)


class DiscoveryError(Exception):
    """Raised when the current Stores/PriceFull file cannot be discovered."""


@dataclass(frozen=True)
class DiscoveredFile:
    """One discovered downloadable file: its signed URL plus discovery
    metadata. Contains no downloaded bytes."""

    filename: str
    url: str
    listing_time_raw: str
    signed_url_expiry_raw: str | None
    discovered_at: datetime


def _extract_signed_expiry(url: str) -> str | None:
    query = urllib.parse.urlsplit(url).query
    values = urllib.parse.parse_qs(query).get("se")
    return values[0] if values else None


def _filename_from_url(url: str) -> str:
    return urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]


def _fetch_listing_html(category_id: int, store_id: str | None) -> str:
    query = urllib.parse.urlencode(
        {"catID": category_id, "storeId": store_id or "0", "sort": "Time", "sortdir": "DESC"}
    )
    request = urllib.request.Request(
        f"{LIST_ENDPOINT_URL}?{query}", headers={"User-Agent": USER_AGENT}
    )

    last_error: Exception | None = None
    for attempt in range(_DISCOVERY_RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body: bytes = response.read()
                return body.decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < _DISCOVERY_RETRY_ATTEMPTS:
                time.sleep(_DISCOVERY_RETRY_BACKOFF_SECONDS)

    raise DiscoveryError(
        f"Could not reach Shufersal listing endpoint for category={category_id} "
        f"store_id={store_id!r} after {_DISCOVERY_RETRY_ATTEMPTS} attempt(s): {last_error}"
    ) from last_error


def _discover_current_file(category_id: int, store_id: str | None) -> DiscoveredFile:
    html = _fetch_listing_html(category_id, store_id)
    match = _ROW_PATTERN.search(html)
    if match is None:
        raise DiscoveryError(
            f"No files listed for category={category_id} store_id={store_id!r}; "
            "the portal returned no matching rows."
        )

    # The portal HTML-escapes '&' as '&amp;' inside the href attribute; it
    # must be unescaped before use, otherwise the signed URL's query string
    # (sig/se/etc.) is corrupted and the blob store rejects it.
    url = unescape(match.group("url"))
    return DiscoveredFile(
        filename=_filename_from_url(url),
        url=url,
        listing_time_raw=match.group("time").strip(),
        signed_url_expiry_raw=_extract_signed_expiry(url),
        discovered_at=datetime.now(UTC),
    )


def discover_stores_file() -> DiscoveredFile:
    """Discover the current Shufersal Stores file.

    Download the returned URL immediately; do not cache or reuse it after
    any delay -- it is a short-lived signed URL.
    """
    return _discover_current_file(CATEGORY_STORES, store_id=None)


def discover_pricefull_file(store_id: str) -> DiscoveredFile:
    """Discover the current Shufersal PriceFull file for one store_id.

    Download the returned URL immediately; do not cache or reuse it after
    any delay -- it is a short-lived signed URL.
    """
    return _discover_current_file(CATEGORY_PRICE_FULL, store_id=store_id)
