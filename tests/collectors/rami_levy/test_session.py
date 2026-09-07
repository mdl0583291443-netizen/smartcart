"""Tests for smartcart.collectors.rami_levy.session.

All deterministic, no network access. `urllib.request.OpenerDirector.open`
is monkeypatched (RamiLevySession calls `self._opener.open(...)`, so this
is the seam that affects every session instance under test without any
production-code change).
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from smartcart.collectors.rami_levy.session import (
    ListingError,
    LoginError,
    RamiLevySession,
    SessionExpiredError,
    _extract_csrf,
)

BASE_URL = "https://fake.publishedprices.example"


class _FakeResponse:
    def __init__(self, body: bytes, url: str, status: int = 200) -> None:
        self._body = body
        self._url = url
        self.status = status

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _login_page_html(csrf: str) -> str:
    return f'<html><meta name="csrftoken" content="{csrf}"/><body>login</body></html>'


def _authenticated_file_page_html(csrf: str, username: str = "RamiLevi") -> str:
    return (
        f'<html><meta name="csrftoken" content="{csrf}"/>'
        f"<body>Logged in as '{username}'</body></html>"
    )


def _listing_json(rows: list[dict[str, object]]) -> bytes:
    return json.dumps({"aaData": rows, "iTotalRecords": str(len(rows))}).encode("utf-8")


# --- CSRF extraction -------------------------------------------------------


def test_extract_csrf_finds_token() -> None:
    html = '<meta name="csrftoken" content="abc123"/>'
    assert _extract_csrf(html) == "abc123"


def test_extract_csrf_returns_none_when_absent() -> None:
    assert _extract_csrf("<html><body>no token here</body></html>") is None


# --- Login: success/failure -------------------------------------------------


def test_login_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()

    assert session._logged_in is True
    assert session._csrf_token == "csrf-2"


def test_login_failure_no_redirect_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            # Login rejected: lands back on /login, not /file.
            return _FakeResponse(
                _login_page_html("csrf-1").encode("utf-8"), url=f"{BASE_URL}/login"
            )
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    with pytest.raises(LoginError):
        session.login()
    assert session._logged_in is False


def test_login_failure_missing_csrf_on_login_page(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        return _FakeResponse(b"<html>no csrf token here</html>", url=request.full_url)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    with pytest.raises(LoginError):
        session.login()


def test_login_failure_missing_authenticated_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            # Redirects to /file (looks right) but no "Logged in as" evidence.
            return _FakeResponse(b"<html>no evidence</html>", url=f"{BASE_URL}/file")
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    with pytest.raises(LoginError):
        session.login()


# --- Root listing must omit "cd" -------------------------------------------


def test_list_directory_root_request_omits_cd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recon showed cd=/ returns an empty-but-well-formed listing, while
    omitting cd entirely returns the real root listing. This locks in that
    the POST body never includes a "cd" key."""
    captured_bodies: list[bytes] = []

    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/json/dir":
            assert isinstance(request.data, bytes)
            captured_bodies.append(request.data)
            return _FakeResponse(_listing_json([]), url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    session.list_directory()

    assert len(captured_bodies) == 1
    body_text = captured_bodies[0].decode("ascii")
    assert "cd=" not in body_text


# --- Session expiry -> one re-login -> retry --------------------------------


def test_list_directory_reauthenticates_once_on_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    login_attempts = {"count": 0}
    listing_attempts = {"count": 0}

    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            login_attempts["count"] += 1
            return _FakeResponse(
                _login_page_html(f"csrf-login-{login_attempts['count']}").encode("utf-8"), url=url
            )
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html(f"csrf-file-{login_attempts['count']}").encode(
                    "utf-8"
                ),
                url=f"{BASE_URL}/file",
            )
        if url == f"{BASE_URL}/file/json/dir":
            listing_attempts["count"] += 1
            if listing_attempts["count"] == 1:
                # Stale session/CSRF: server reports an error, HTTP 200.
                return _FakeResponse(
                    json.dumps({"error": "CSRF security check failed"}).encode("utf-8"), url=url
                )
            return _FakeResponse(
                _listing_json([{"fname": "Stores1-000-20260907-000000.xml"}]), url=url
            )
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    rows = session.list_directory()

    assert login_attempts["count"] == 2  # initial + exactly one re-login
    assert listing_attempts["count"] == 2  # failed once, succeeded on retry
    assert session.relogin_count == 1
    assert rows == [{"fname": "Stores1-000-20260907-000000.xml"}]


def test_list_directory_relogin_failure_does_not_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the re-login itself fails, that error propagates -- no infinite
    retry loop, and no further listing attempt is made."""
    login_attempts = {"count": 0}
    listing_attempts = {"count": 0}

    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            login_attempts["count"] += 1
            return _FakeResponse(_login_page_html("csrf-login").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            if login_attempts["count"] == 1:
                # First login succeeds.
                return _FakeResponse(
                    _authenticated_file_page_html("csrf-file-1").encode("utf-8"),
                    url=f"{BASE_URL}/file",
                )
            # Re-login attempt fails (rejected, lands back on /login).
            return _FakeResponse(
                _login_page_html("csrf-login").encode("utf-8"), url=f"{BASE_URL}/login"
            )
        if url == f"{BASE_URL}/file/json/dir":
            listing_attempts["count"] += 1
            return _FakeResponse(
                json.dumps({"error": "CSRF security check failed"}).encode("utf-8"), url=url
            )
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    with pytest.raises(LoginError):
        session.list_directory()

    assert login_attempts["count"] == 2  # initial success + one failed re-login attempt
    assert listing_attempts["count"] == 1  # only the first (failed) listing attempt


def test_list_directory_401_is_session_expired_not_listing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/json/dir":
            return _FakeResponse(b"", url=url, status=401)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    # Both the first attempt and the retry-after-relogin return 401, so the
    # error from the final attempt (SessionExpiredError) propagates.
    with pytest.raises(SessionExpiredError):
        session.list_directory()


def test_list_directory_malformed_json_is_listing_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/json/dir":
            return _FakeResponse(b"not json at all", url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    with pytest.raises(ListingError):
        session.list_directory()


# --- Download --------------------------------------------------------------


def test_download_file_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/d/Stores1-000-20260907-000000.xml":
            return _FakeResponse(b"<Root></Root>", url=url)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    body = session.download_file("Stores1-000-20260907-000000.xml")
    assert body == b"<Root></Root>"


def test_download_file_redirected_to_login_is_session_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_open(
        self: object, request: urllib.request.Request, timeout: float = 0
    ) -> _FakeResponse:
        url = request.full_url
        if url == f"{BASE_URL}/login":
            return _FakeResponse(_login_page_html("csrf-1").encode("utf-8"), url=url)
        if url == f"{BASE_URL}/login/user":
            return _FakeResponse(
                _authenticated_file_page_html("csrf-2").encode("utf-8"), url=f"{BASE_URL}/file"
            )
        if url == f"{BASE_URL}/file/d/some-file.gz":
            return _FakeResponse(b"<html>login form</html>", url=f"{BASE_URL}/login")
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)

    session = RamiLevySession(BASE_URL)
    session.login()
    with pytest.raises(SessionExpiredError):
        session.download_file("some-file.gz")
