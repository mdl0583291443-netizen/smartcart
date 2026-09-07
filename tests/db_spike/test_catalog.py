"""Store identity correction tests.

Store has a SmartCart-owned, opaque surrogate identity. No retailer raw
store identifier may act as Store's semantic canonical identity -- ALL
retailer/source-specific raw store identifiers live in
store_source_alias, preserved exactly. For Rami Levy, both "039"
(filename/catalog token) and "39" (the online-family PriceFull XML's own
carried value, see docs/adr/0007) must be representable as exact source
aliases for the SAME Store, with neither privileged as canonical.
"""

from __future__ import annotations

import pg8000.native

from smartcart.db_spike.catalog import (
    add_store_source_alias,
    get_or_create_store_by_alias,
    store_source_aliases,
    upsert_chain,
    upsert_chain_product,
    upsert_subchain,
)

_CHAIN_ID = "7290058140886"
_SUBCHAIN_ID = "001"


def _seed_chain(conn: pg8000.native.Connection) -> None:
    upsert_chain(conn, chain_id=_CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(conn, chain_id=_CHAIN_ID, subchain_id=_SUBCHAIN_ID, subchain_name="Test Sub")


def test_store_identity_is_an_opaque_surrogate_not_a_retailer_raw_value(
    db_conn: pg8000.native.Connection,
) -> None:
    """Required focused test (Store identity correction): one Store row
    with opaque SmartCart identity, alias "039", alias "39", both map to
    the same Store, raw values round-trip unchanged, and no retailer raw
    identifier is stored as Store's semantic identity."""
    _seed_chain(db_conn)

    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value="039",
        store_name="Online Store",
    )

    # Store's own identity is an opaque surrogate: an auto-generated
    # integer, never the retailer's raw string "039".
    assert isinstance(store_id, int)

    store_row = db_conn.run(
        "SELECT store_id, chain_id, subchain_id, store_name FROM store WHERE store_id = :store_id",
        store_id=store_id,
    )
    assert len(store_row) == 1
    assert store_row[0][0] == store_id
    assert store_row[0][1] == _CHAIN_ID
    assert store_row[0][2] == _SUBCHAIN_ID
    # Confirm directly against the schema: 'store' has no column at all
    # that holds a retailer-shaped raw identifier as identity.
    columns = {
        row[0]
        for row in db_conn.run(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'store'"
        )
    }
    assert columns == {"store_id", "chain_id", "subchain_id", "store_name"}

    # A second, distinct raw identifier for the SAME physical store (the
    # online PriceFull family's own XML-carried "39") is recorded as an
    # additional alias for the same store_id -- never rewriting "039".
    add_store_source_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        source="rami_levy",
        alias_context="xml_store_id_online",
        raw_value="39",
    )

    aliases = store_source_aliases(db_conn, store_id=store_id)
    assert aliases == [
        ("rami_levy", "filename_store_id", "039"),
        ("rami_levy", "xml_store_id_online", "39"),
    ]
    # Both raw values round-trip exactly, unchanged, as strings.
    raw_values = {raw_value for (_, _, raw_value) in aliases}
    assert raw_values == {"039", "39"}
    for _, _, raw_value in aliases:
        assert isinstance(raw_value, str)


def test_get_or_create_store_by_alias_is_idempotent_for_the_same_raw_identifier(
    db_conn: pg8000.native.Connection,
) -> None:
    _seed_chain(db_conn)

    first_store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value="039",
    )
    second_store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value="039",
    )

    assert first_store_id == second_store_id
    store_count = db_conn.run("SELECT count(*) FROM store")[0][0]
    assert store_count == 1


def test_adding_the_same_alias_twice_is_idempotent_not_duplicated(
    db_conn: pg8000.native.Connection,
) -> None:
    _seed_chain(db_conn)
    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value="039",
    )

    for _ in range(2):
        add_store_source_alias(
            db_conn,
            chain_id=_CHAIN_ID,
            store_id=store_id,
            source="rami_levy",
            alias_context="xml_store_id_online",
            raw_value="39",
        )

    aliases = store_source_aliases(db_conn, store_id=store_id)
    assert aliases.count(("rami_levy", "xml_store_id_online", "39")) == 1


def test_two_different_raw_identifiers_from_different_sources_can_map_to_one_store(
    db_conn: pg8000.native.Connection,
) -> None:
    """A store observed by two different collectors under two entirely
    different raw identifiers still resolves to one Store once both
    aliases are known, without either raw value being treated as more
    canonical than the other."""
    _seed_chain(db_conn)

    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        subchain_id=_SUBCHAIN_ID,
        source="rami_levy",
        alias_context="filename_store_id",
        raw_value="039",
    )
    add_store_source_alias(
        db_conn,
        chain_id=_CHAIN_ID,
        store_id=store_id,
        source="rami_levy",
        alias_context="xml_store_id_online",
        raw_value="39",
    )

    store_count = db_conn.run("SELECT count(*) FROM store")[0][0]
    assert store_count == 1
    assert len(store_source_aliases(db_conn, store_id=store_id)) == 2


def test_chain_product_preserves_item_code_raw_exactly(db_conn: pg8000.native.Connection) -> None:
    upsert_chain(db_conn, chain_id=_CHAIN_ID, chain_name="Test Chain")

    zero_prefixed_code = "0010181040009"  # a leading zero must survive as a string
    upsert_chain_product(db_conn, chain_id=_CHAIN_ID, item_code_raw=zero_prefixed_code)

    stored = db_conn.run(
        "SELECT item_code_raw FROM chain_product WHERE chain_id = :chain_id",
        chain_id=_CHAIN_ID,
    )
    assert stored == [[zero_prefixed_code]]
    assert isinstance(stored[0][0], str)
