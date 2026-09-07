"""Rami Levy session management: login, CSRF handling, and session-cookie
based authenticated HTTP calls against the public PublishedPrices portal.

Observed public flow (see docs/adr/0006 for the endpoint itself):

    GET  /login          -> sets a session cookie, page carries a
                             session-bound CSRF token
    POST /login/user     -> username=RamiLevi, password="", csrftoken=...
                             -> redirects to /file on success

One session object is used per run. Session expiry is detected reactively
on authenticated operations (an HTTP 401/403, a redirect back to /login, or
a JSON response carrying an "error" key) -- never by assuming a TTL. On
detected expiry, exactly one fresh login is attempted and the failed
operation is retried exactly once; if that also fails, the error from that
second attempt propagates. There is no unbounded retry loop anywhere here.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import TypeVar

from smartcart.collectors.rami_levy.config import (
    PROVIDER_PASSWORD,
    PROVIDER_USERNAME,
    get_provider_base_url,
)

USER_AGENT = "SmartCart-RamiLevy-Collector/1.0"
REQUEST_TIMEOUT_SECONDS = 30.0

_LOGIN_RETRY_ATTEMPTS = 2
_LOGIN_RETRY_BACKOFF_SECONDS = 1.0

# Comfortably above the largest total-file-count observed in reconnaissance
# (~2100). Not pagination -- the live API returns everything in one page
# when asked for a page this large; if that ever stops being true, the
# listing would simply come back incomplete rather than erroring, which is
# a discovery-layer concern (see discovery.py), not this module's.
_LISTING_PAGE_SIZE = 10000

_CSRF_TOKEN_RE = re.compile(r'name="csrftoken"\s+content="([^"]*)"')

T = TypeVar("T")


class LoginError(Exception):
    """Raised when initial login/session establishment fails."""


class SessionExpiredError(Exception):
    """Raised internally when an authenticated call is detected as no
    longer authenticated (401/403, redirect to /login, or a JSON error)."""


class ListingError(Exception):
    """Raised when the directory-listing response cannot be interpreted as
    a file list at all (not an auth problem -- see SessionExpiredError)."""


def _extract_csrf(html: str) -> str | None:
    match = _CSRF_TOKEN_RE.search(html)
    return match.group(1) if match else None


class RamiLevySession:
    """One authenticated session against the Rami Levy provider portal."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or get_provider_base_url()).rstrip("/")
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar)
        )
        self._csrf_token: str | None = None
        self._logged_in = False
        self.relogin_count = 0

    def _get(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with self._opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body: bytes = response.read()
        return body.decode("utf-8", errors="replace")

    def login(self) -> None:
        """Establish a fresh session. Bounded retry for transient network
        failures only; a definitive rejection (no CSRF, no redirect to
        /file, no authenticated-page evidence) is not retried."""
        last_error: Exception | None = None
        for attempt in range(_LOGIN_RETRY_ATTEMPTS):
            try:
                self._do_login()
                self._logged_in = True
                return
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt + 1 < _LOGIN_RETRY_ATTEMPTS:
                    time.sleep(_LOGIN_RETRY_BACKOFF_SECONDS)

        self._logged_in = False
        raise LoginError(
            f"Could not reach the Rami Levy login endpoint after "
            f"{_LOGIN_RETRY_ATTEMPTS} attempt(s): {last_error}"
        ) from last_error

    def _do_login(self) -> None:
        login_html = self._get(f"{self.base_url}/login")
        csrf = _extract_csrf(login_html)
        if csrf is None:
            raise LoginError("Could not extract a CSRF token from the Rami Levy login page.")

        data = urllib.parse.urlencode(
            {
                "username": PROVIDER_USERNAME,
                "password": PROVIDER_PASSWORD,
                "r": "",
                "csrftoken": csrf,
            }
        ).encode("ascii")
        request = urllib.request.Request(
            f"{self.base_url}/login/user", data=data, headers={"User-Agent": USER_AGENT}
        )
        with self._opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            body = response.read().decode("utf-8", errors="replace")

        if not final_url.rstrip("/").endswith("/file"):
            raise LoginError(
                f"Login did not redirect to /file as expected (landed on {final_url!r})."
            )

        logged_in_marker = f"Logged in as '{PROVIDER_USERNAME}'"
        if logged_in_marker not in body:
            raise LoginError(
                "Login response did not contain authenticated-page evidence "
                f"({logged_in_marker!r} not found)."
            )

        csrf2 = _extract_csrf(body)
        if csrf2 is None:
            raise LoginError("Could not extract a session-bound CSRF token after login.")
        self._csrf_token = csrf2

    def _with_reauth(self, fn: Callable[[], T]) -> T:
        if not self._logged_in:
            self.login()
        try:
            return fn()
        except SessionExpiredError:
            self.relogin_count += 1
            self.login()
            return fn()  # retry exactly once; propagate whatever this raises

    def list_directory(self) -> list[dict[str, object]]:
        """Return the full directory listing (all rows in one request --
        see _LISTING_PAGE_SIZE). Root listing must never send `cd`: sending
        `cd=/` was observed to return an empty-but-well-formed listing,
        while omitting `cd` entirely returns the real root listing."""
        return self._with_reauth(self._list_directory_once)

    def _list_directory_once(self) -> list[dict[str, object]]:
        if self._csrf_token is None:
            raise SessionExpiredError("No CSRF token available; session not established.")

        # Deliberately no "cd" key at all -- see docstring above.
        data = urllib.parse.urlencode(
            {
                "csrftoken": self._csrf_token,
                "iDisplayStart": "0",
                "iDisplayLength": str(_LISTING_PAGE_SIZE),
            }
        ).encode("ascii")
        request = urllib.request.Request(
            f"{self.base_url}/file/json/dir", data=data, headers={"User-Agent": USER_AGENT}
        )
        with self._opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            status = response.status
            raw_body = response.read()

        if status in (401, 403):
            raise SessionExpiredError(f"Listing request returned HTTP {status}.")
        if "/login" in final_url and not final_url.rstrip("/").endswith("/file/json/dir"):
            raise SessionExpiredError(f"Listing request was redirected to {final_url!r}.")

        try:
            payload = json.loads(raw_body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ListingError(f"Listing response was not valid JSON: {exc}") from exc

        if isinstance(payload, dict) and payload.get("error"):
            raise SessionExpiredError(f"Listing request reported an error: {payload['error']!r}")

        rows = payload.get("aaData") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ListingError("Listing response did not contain an 'aaData' array.")
        return rows

    def download_file(self, filename: str) -> bytes:
        return self._with_reauth(lambda: self._download_file_once(filename))

    def _download_file_once(self, filename: str) -> bytes:
        url = f"{self.base_url}/file/d/{urllib.parse.quote(filename)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with self._opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            status = response.status
            body: bytes = response.read()

        if status in (401, 403):
            raise SessionExpiredError(f"Download request for {filename!r} returned HTTP {status}.")
        if "/login" in final_url:
            raise SessionExpiredError(
                f"Download request for {filename!r} was redirected to {final_url!r}."
            )
        return body
