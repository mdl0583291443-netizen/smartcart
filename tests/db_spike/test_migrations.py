"""Round 1 test 1: an empty database can be constructed entirely from
migrations, reproducibly."""

from __future__ import annotations

import pg8000.native

from smartcart.db_spike import migrate

_EXPECTED_TABLES = {
    "artifact_content",
    "artifact_occurrence",
    "chain",
    "chain_product",
    "chain_product_assignment_history",
    "chain_product_current_assignment",
    "ingestion_run",
    "price_history",
    "smartcart_product",
    "store",
    "store_product_current_state",
    "store_source_alias",
    "subchain",
}


def test_migrations_are_idempotent_on_an_already_migrated_database(
    db_conn: pg8000.native.Connection,
) -> None:
    # The db_conn fixture already applied migrations once; re-applying
    # against the same database must be a no-op.
    applied_again = migrate.apply_migrations(db_conn)
    assert applied_again == []


def test_migrations_create_exactly_the_expected_tables(db_conn: pg8000.native.Connection) -> None:
    rows = db_conn.run(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name != 'schema_migrations' "
        "ORDER BY table_name"
    )
    assert {row[0] for row in rows} == _EXPECTED_TABLES


def test_migrations_are_tracked_in_schema_migrations(db_conn: pg8000.native.Connection) -> None:
    rows = db_conn.run("SELECT version FROM schema_migrations ORDER BY version")
    assert [row[0] for row in rows] == [
        "0001_initial_schema.sql",
        "0002_round2_activation.sql",
        "0003_activation_outcome.sql",
        "0004_normalized_current_state_facts.sql",
        "0005_product_identity_slice_a.sql",
        "0006_product_identity_current_assignment.sql",
        "0007_chain_product_assignment_history.sql",
    ]
