"""Downloading discovered Rami Levy files via the authenticated session.

Session/authentication concerns (login, CSRF, expiry detection, the bounded
one-retry-after-relogin behavior) live in session.py -- this module only
adds the "explicitly reject empty/bad response bodies" download-stage
check on top, mirroring the same responsibility split used for Shufersal.
"""

from __future__ import annotations

from smartcart.collectors.rami_levy.session import RamiLevySession

_MIN_PLAUSIBLE_BODY_BYTES = 1


class DownloadError(Exception):
    """Raised when a discovered file's body is empty."""


def download_bytes(session: RamiLevySession, filename: str) -> bytes:
    """Download the raw bytes for a discovered filename.

    Session-level failures (LoginError, SessionExpiredError after the
    session's own bounded re-login-and-retry) propagate unchanged from
    `session.download_file`; this function only adds the empty-body check.
    """
    body = session.download_file(filename)
    if len(body) < _MIN_PLAUSIBLE_BODY_BYTES:
        raise DownloadError(f"Downloaded body for {filename!r} was empty ({len(body)} bytes).")
    return body
