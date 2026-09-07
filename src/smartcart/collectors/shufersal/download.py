"""Downloading discovered Shufersal files.

Byte-level HTTP concerns only. Transport (gzip) and XML parsing are
handled by transport.py / parse.py respectively. This module distinguishes
three failure modes so callers (run.py) know how to react:

- DownloadNetworkError: transient network/HTTP failure. This module already
  retries once internally before raising it.
- DownloadAuthExpiredError: the signed URL was rejected as expired/invalid
  (HTTP 401/403). This module never retries the same URL on this error --
  the caller must rediscover a fresh URL instead.
- DownloadEmptyBodyError: the server returned HTTP 200 with an empty body.
  This is not retried; a repeat request would be handed the same result.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from smartcart.collectors.shufersal.discovery import DiscoveredFile

USER_AGENT = "SmartCart-Shufersal-Collector/1.0"
REQUEST_TIMEOUT_SECONDS = 60.0

_MIN_PLAUSIBLE_BODY_BYTES = 1

_DOWNLOAD_RETRY_ATTEMPTS = 2
_DOWNLOAD_RETRY_BACKOFF_SECONDS = 1.0

_AUTH_EXPIRED_STATUS_CODES = frozenset({401, 403})


class DownloadError(Exception):
    """Base for download-stage failures (module-local; no shared hierarchy
    with transport/parse errors)."""


class DownloadNetworkError(DownloadError):
    """Transient network/HTTP failure; already retried once internally."""


class DownloadAuthExpiredError(DownloadError):
    """The signed URL was rejected as expired/invalid; do not retry as-is."""


class DownloadEmptyBodyError(DownloadError):
    """HTTP 200 but the response body was empty."""


def _validate_body(body: bytes, filename: str) -> bytes:
    if len(body) < _MIN_PLAUSIBLE_BODY_BYTES:
        raise DownloadEmptyBodyError(
            f"Downloaded body for {filename!r} was empty ({len(body)} bytes)."
        )
    return body


def download_bytes(discovered: DiscoveredFile) -> bytes:
    """Download the raw bytes for a just-discovered file.

    Performs one bounded retry for transient network failures. Raises
    DownloadAuthExpiredError (without retrying) if the signed URL is
    rejected as expired/invalid, so the caller can rediscover a fresh one.
    Raises DownloadEmptyBodyError (without retrying) for an empty body.
    """
    request = urllib.request.Request(discovered.url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None

    for attempt in range(_DOWNLOAD_RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body: bytes = response.read()
            return _validate_body(body, discovered.filename)
        except urllib.error.HTTPError as exc:
            if exc.code in _AUTH_EXPIRED_STATUS_CODES:
                raise DownloadAuthExpiredError(
                    f"Signed URL rejected (HTTP {exc.code}) for {discovered.filename!r}; "
                    "rediscover instead of retrying."
                ) from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc

        if attempt + 1 < _DOWNLOAD_RETRY_ATTEMPTS:
            time.sleep(_DOWNLOAD_RETRY_BACKOFF_SECONDS)

    raise DownloadNetworkError(
        f"Could not download {discovered.filename!r} after "
        f"{_DOWNLOAD_RETRY_ATTEMPTS} attempt(s): {last_error}"
    ) from last_error
