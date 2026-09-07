"""Minimal, version-tracked SQL migration runner for the Focused DB Spike.

Not a production zero-downtime migration framework (see
docs/adr/0009-focused-db-spike.md) -- applies numbered .sql files from
migrations/ in filename order, recording each in a schema_migrations
table, so the spike database can be constructed reproducibly from an
empty state.
"""

from __future__ import annotations

from pathlib import Path

import pg8000.native

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def _pending_migrations(conn: pg8000.native.Connection) -> list[Path]:
    applied = {row[0] for row in conn.run("SELECT version FROM schema_migrations")}
    return [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.name not in applied]


def apply_migrations(conn: pg8000.native.Connection) -> list[str]:
    """Apply all not-yet-applied migrations, in filename order, each in its
    own transaction. Returns the filenames just applied (empty if the
    database was already up to date)."""
    conn.run(_CREATE_TRACKING_TABLE)
    applied_now: list[str] = []
    for path in _pending_migrations(conn):
        sql = path.read_text(encoding="utf-8")
        conn.run("begin")
        try:
            conn.run(sql)
            conn.run("INSERT INTO schema_migrations (version) VALUES (:version)", version=path.name)
        except BaseException:
            conn.run("rollback")
            raise
        else:
            conn.run("commit")
        applied_now.append(path.name)
    return applied_now
