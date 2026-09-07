"""Connection/DSN handling and explicit transaction control for the
Focused DB Spike.

See docs/adr/0009-focused-db-spike.md for why pg8000 was chosen. pg8000
auto-commits each statement by default (there is no ambient transaction
unless one is opened explicitly) -- `transaction()` is the one place in
this package that changes that, and every write that must be atomic (see
Fixed Data Invariant 7) must run inside it.
"""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager

import pg8000.native

DSN_ENV_VAR = "SMARTCART_DB_SPIKE_DSN"


def get_dsn() -> str:
    """Return the configured spike database DSN (a postgresql:// URI).

    Raises RuntimeError if unset -- this spike has no default connection
    target; tests supply one from an ephemeral pgserver instance (see
    tests/db_spike/conftest.py).
    """
    dsn = os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise RuntimeError(
            f"{DSN_ENV_VAR} is not set; the Focused DB Spike has no default "
            "connection target (see docs/adr/0009)."
        )
    return dsn


def connect(dsn: str | None = None) -> pg8000.native.Connection:
    """Open one connection to the spike database from a postgresql:// URI.

    Most URIs name a TCP host via `parsed.hostname`. Some servers (e.g.
    pgserver on Linux/WSL) instead publish a Unix-domain socket directory
    in the `host` query parameter, per libpq convention -- pg8000 has no
    equivalent of that convention, so it must be translated into the full
    socket file path (`<dir>/.s.PGSQL.<port>`) it expects as `unix_sock`.
    """
    parsed = urllib.parse.urlsplit(dsn or get_dsn())
    query_host = urllib.parse.parse_qs(parsed.query).get("host", [None])[0]
    connect_kwargs: dict[str, object]
    if query_host and query_host.startswith("/"):
        port = parsed.port or 5432
        connect_kwargs = {"unix_sock": f"{query_host}/.s.PGSQL.{port}"}
    else:
        connect_kwargs = {"host": parsed.hostname, "port": parsed.port}

    return pg8000.native.Connection(
        user=parsed.username or "postgres",
        password=parsed.password or "",
        database=parsed.path.lstrip("/") or "postgres",
        **connect_kwargs,
    )


@contextmanager
def transaction(conn: pg8000.native.Connection) -> Iterator[None]:
    """Run the enclosed block as one atomic transaction: BEGIN on enter,
    COMMIT on clean exit, ROLLBACK if the block raises."""
    conn.run("begin")
    try:
        yield
    except BaseException:
        conn.run("rollback")
        raise
    else:
        conn.run("commit")
