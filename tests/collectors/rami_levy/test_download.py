"""Tests for smartcart.collectors.rami_levy.download.

All deterministic, no network access.
"""

from __future__ import annotations

import pytest

from smartcart.collectors.rami_levy.download import DownloadError, download_bytes
from smartcart.collectors.rami_levy.session import RamiLevySession


def test_download_bytes_returns_body_when_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = RamiLevySession("https://fake.example")
    monkeypatch.setattr(session, "download_file", lambda filename: b"<Root></Root>")

    assert download_bytes(session, "Stores1-000-20260907-000000.xml") == b"<Root></Root>"


def test_download_bytes_raises_on_empty_body(monkeypatch: pytest.MonkeyPatch) -> None:
    session = RamiLevySession("https://fake.example")
    monkeypatch.setattr(session, "download_file", lambda filename: b"")

    with pytest.raises(DownloadError):
        download_bytes(session, "Stores1-000-20260907-000000.xml")
