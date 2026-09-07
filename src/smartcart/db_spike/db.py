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
    """Open one connection to the spike database from a postgresql:// URI."""
    parsed = urllib.parse.urlsplit(dsn or get_dsn())
    return pg8000.native.Connection(
        user=parsed.username or "postgres",
        password=parsed.password or "",
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path.lstrip("/") or "postgres",
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
