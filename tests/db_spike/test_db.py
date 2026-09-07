"""Unit tests for DSN parsing / connection argument selection in
smartcart.db_spike.db.connect().

These exercise connect()'s argument translation in isolation (no real
Postgres needed) by patching pg8000.native.Connection and inspecting the
kwargs it was called with.
"""

from __future__ import annotations

from unittest.mock import patch

from smartcart.db_spike.db import connect


def test_connect_passes_tcp_host_and_port_unchanged() -> None:
    with patch("smartcart.db_spike.db.pg8000.native.Connection") as mock_conn:
        connect("postgresql://alice:secret@dbhost:5433/mydb")

    mock_conn.assert_called_once_with(
        user="alice",
        password="secret",
        database="mydb",
        host="dbhost",
        port=5433,
    )


def test_connect_defaults_user_password_and_database_for_tcp_uri() -> None:
    with patch("smartcart.db_spike.db.pg8000.native.Connection") as mock_conn:
        connect("postgresql://dbhost/")

    mock_conn.assert_called_once_with(
        user="postgres",
        password="",
        database="postgres",
        host="dbhost",
        port=None,
    )


def test_connect_translates_unix_socket_directory_query_param() -> None:
    # This is the exact shape pgserver 0.1.4 returns on Linux/WSL: an
    # empty hostname with the real (Unix-domain socket directory) address
    # carried in the `host` query parameter instead.
    dsn = "postgresql://postgres:@/postgres?host=/tmp/smartcart-check-xxxx"

    with patch("smartcart.db_spike.db.pg8000.native.Connection") as mock_conn:
        connect(dsn)

    mock_conn.assert_called_once_with(
        user="postgres",
        password="",
        database="postgres",
        unix_sock="/tmp/smartcart-check-xxxx/.s.PGSQL.5432",
    )


def test_connect_uses_explicit_port_for_unix_socket_when_given() -> None:
    # The port, when present, is still the URI's own port component (as
    # for a TCP URI) -- it does not move into the query string.
    dsn = "postgresql://postgres:@:5555/postgres?host=/tmp/smartcart-check-xxxx"

    with patch("smartcart.db_spike.db.pg8000.native.Connection") as mock_conn:
        connect(dsn)

    mock_conn.assert_called_once_with(
        user="postgres",
        password="",
        database="postgres",
        unix_sock="/tmp/smartcart-check-xxxx/.s.PGSQL.5555",
    )
