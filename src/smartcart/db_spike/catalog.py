"""Chain/Subchain/Store/StoreSourceAlias/ChainProduct identity: minimal,
source-faithful upserts.

Store has a SmartCart-owned, opaque surrogate identity (`store.store_id`,
a bigint). No retailer raw store identifier is or ever influences that
identity -- there is no "canonical raw store id" concept anywhere in this
module. ALL retailer/source-specific raw store identifiers -- including,
for one Rami Levy store, both "039" (filename/catalog token) and "39"
(the online-family PriceFull XML's own carried value, see docs/adr/0007)
-- live in `store_source_alias`, preserved exactly, never rewritten into
one another and never written into `store` itself.

Because Store identity is opaque, resolving "which Store does this raw
identifier refer to" requires going through the alias table:
`get_or_create_store_by_alias` is the entry point a caller uses the first
time it sees a raw identifier for a store; `add_store_source_alias`
records an additional known alias for an already-resolved store (e.g.
once a store created via its filename/catalog token is later also seen
under a different raw value in a different source context).
"""

from __future__ import annotations

import pg8000.native

from smartcart.db_spike.db import transaction


def upsert_chain(conn: pg8000.native.Connection, *, chain_id: str, chain_name: str | None) -> None:
    conn.run(
        """
        INSERT INTO chain (chain_id, chain_name) VALUES (:chain_id, :chain_name)
        ON CONFLICT (chain_id) DO UPDATE SET chain_name = excluded.chain_name
        """,
        chain_id=chain_id,
        chain_name=chain_name,
    )


def upsert_subchain(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    subchain_id: str,
    subchain_name: str | None,
) -> None:
    conn.run(
        """
        INSERT INTO subchain (chain_id, subchain_id, subchain_name)
        VALUES (:chain_id, :subchain_id, :subchain_name)
        ON CONFLICT (chain_id, subchain_id) DO UPDATE SET subchain_name = excluded.subchain_name
        """,
        chain_id=chain_id,
        subchain_id=subchain_id,
        subchain_name=subchain_name,
    )


def get_or_create_store_by_alias(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    subchain_id: str,
    source: str,
    alias_context: str,
    raw_value: str,
    store_name: str | None = None,
) -> int:
    """Resolve the SmartCart-owned store_id for a raw source-observed
    identifier, creating a new Store (and recording this as its first
    alias) the first time this exact (chain_id, source, alias_context,
    raw_value) tuple is seen. Returns the existing store_id unchanged on
    every subsequent call with the same tuple -- Store is never
    duplicated for an identifier already resolved.

    Runs as one transaction so the alias lookup, Store creation, and
    alias recording cannot race: two concurrent callers resolving the
    same raw identifier for the first time cannot create two Store rows.
    """
    with transaction(conn):
        existing = conn.run(
            """
            SELECT store_id FROM store_source_alias
            WHERE chain_id = :chain_id AND source = :source
              AND alias_context = :alias_context AND raw_value = :raw_value
            """,
            chain_id=chain_id,
            source=source,
            alias_context=alias_context,
            raw_value=raw_value,
        )
        if existing:
            store_id: int = existing[0][0]
            return store_id

        created = conn.run(
            """
            INSERT INTO store (chain_id, subchain_id, store_name)
            VALUES (:chain_id, :subchain_id, :store_name)
            RETURNING store_id
            """,
            chain_id=chain_id,
            subchain_id=subchain_id,
            store_name=store_name,
        )
        new_store_id: int = created[0][0]

        conn.run(
            """
            INSERT INTO store_source_alias (chain_id, store_id, source, alias_context, raw_value)
            VALUES (:chain_id, :store_id, :source, :alias_context, :raw_value)
            """,
            chain_id=chain_id,
            store_id=new_store_id,
            source=source,
            alias_context=alias_context,
            raw_value=raw_value,
        )
        return new_store_id


def add_store_source_alias(
    conn: pg8000.native.Connection,
    *,
    chain_id: str,
    store_id: int,
    source: str,
    alias_context: str,
    raw_value: str,
) -> None:
    """Record one additional raw, source-observed identifier variant for
    an already-resolved Store, without mutating store_id or raw_value and
    without treating either as more canonical than the other. Idempotent:
    re-adding the identical (chain_id, source, alias_context, raw_value)
    tuple is a no-op, not a duplicate row.
    """
    conn.run(
        """
        INSERT INTO store_source_alias (chain_id, store_id, source, alias_context, raw_value)
        VALUES (:chain_id, :store_id, :source, :alias_context, :raw_value)
        ON CONFLICT (chain_id, source, alias_context, raw_value) DO NOTHING
        """,
        chain_id=chain_id,
        store_id=store_id,
        source=source,
        alias_context=alias_context,
        raw_value=raw_value,
    )


def store_source_aliases(
    conn: pg8000.native.Connection, *, store_id: int
) -> list[tuple[str, str, str]]:
    """Test/inspection helper: (source, alias_context, raw_value) rows for
    one Store, exactly as stored -- never normalized."""
    rows = conn.run(
        """
        SELECT source, alias_context, raw_value FROM store_source_alias
        WHERE store_id = :store_id
        ORDER BY source, alias_context
        """,
        store_id=store_id,
    )
    return [(row[0], row[1], row[2]) for row in rows]


def upsert_chain_product(
    conn: pg8000.native.Connection, *, chain_id: str, item_code_raw: str
) -> None:
    """Thin chain-scoped identity: item_code_raw is stored exactly as the
    chain's own source represents it -- never parsed as a barcode, never
    coerced to an int (Fixed Data Invariant 9)."""
    conn.run(
        """
        INSERT INTO chain_product (chain_id, item_code_raw) VALUES (:chain_id, :item_code_raw)
        ON CONFLICT (chain_id, item_code_raw) DO NOTHING
        """,
        chain_id=chain_id,
        item_code_raw=item_code_raw,
    )
