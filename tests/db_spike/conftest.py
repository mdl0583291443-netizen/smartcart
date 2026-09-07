"""Shared fixtures for Focused DB Spike tests.

Boots one real, disposable PostgreSQL 16 instance via pgserver for the
whole test session (see docs/adr/0009-focused-db-spike.md for why:
neither PostgreSQL nor Docker is available on this project's development
environment, and SQLite would not exercise the real Postgres transaction/
locking semantics these invariants depend on). Each test gets its own
connection with migrations applied and every table truncated first, so
tests are isolated from each other without paying to boot a fresh server
per test.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator

import pg8000.native
import pytest
from pgserver.postgres_server import PostgresServer, get_server

from smartcart.db_spike import migrate
from smartcart.db_spike.db import connect

_TABLES_IN_DEPENDENCY_ORDER = (
    "price_history",
    "store_product_current_state",
    "chain_product",
    "artifact_occurrence",
    "ingestion_run",
    "artifact_content",
    "store_source_alias",
    "store",
    "subchain",
    "chain",
)


@pytest.fixture(scope="session")
def _pg_server() -> Iterator[PostgresServer]:
    with tempfile.TemporaryDirectory(prefix="smartcart-db-spike-pg-") as data_dir:
        server = get_server(data_dir, cleanup_mode="stop")
        try:
            yield server
        finally:
            server.cleanup()


@pytest.fixture
def db_conn(_pg_server: PostgresServer) -> Iterator[pg8000.native.Connection]:
    conn = connect(_pg_server.get_uri())
    try:
        migrate.apply_migrations(conn)
        _truncate_all_tables(conn)
        yield conn
    finally:
        conn.close()


def _truncate_all_tables(conn: pg8000.native.Connection) -> None:
    conn.run("TRUNCATE " + ", ".join(_TABLES_IN_DEPENDENCY_ORDER) + " RESTART IDENTITY CASCADE")
