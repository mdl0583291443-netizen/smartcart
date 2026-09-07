"""Shared seeding helpers for Round 2 activation tests.

Not a test_*.py module -- pytest does not collect this file itself, only
the test files that import from it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pg8000.native

from smartcart.db_spike.activation import ProductPrice
from smartcart.db_spike.catalog import (
    get_or_create_store_by_alias,
    upsert_chain,
    upsert_chain_product,
    upsert_subchain,
)
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import insert_occurrence

CHAIN_ID = "7290027600007"
SUBCHAIN_ID = "002"
ITEM_CODE_RAW = "10181040009"
ITEM_CODE_RAW_2 = "20202020002"


def collected_at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 7, hour, minute, 0, tzinfo=UTC)


def seed_store(conn: pg8000.native.Connection, *, filename_store_token: str = "413") -> int:
    upsert_chain(conn, chain_id=CHAIN_ID, chain_name="Test Chain")
    upsert_subchain(conn, chain_id=CHAIN_ID, subchain_id=SUBCHAIN_ID, subchain_name="Test Sub")
    return get_or_create_store_by_alias(
        conn,
        chain_id=CHAIN_ID,
        subchain_id=SUBCHAIN_ID,
        source="shufersal",
        alias_context="filename_store_id",
        raw_value=filename_store_token,
        store_name="Test Store",
    )


def seed_products(
    conn: pg8000.native.Connection, *, item_codes: tuple[str, ...] = (ITEM_CODE_RAW,)
) -> None:
    for code in item_codes:
        upsert_chain_product(conn, chain_id=CHAIN_ID, item_code_raw=code)


def make_occurrence(
    conn: pg8000.native.Connection, *, store_id: int, collected_at_value: datetime
) -> int:
    payload = f"<Root>{store_id}:{collected_at_value.isoformat()}:{id(object())}</Root>".encode()
    content = insert_or_get_content(conn, payload)
    occurrence = insert_occurrence(
        conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=CHAIN_ID,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename="PriceFull...gz",
        schema_family=None,
        collected_at=collected_at_value,
        validation_status="valid",
    )
    return occurrence.occurrence_id


def price(value: str, *, item_code_raw: str = ITEM_CODE_RAW) -> ProductPrice:
    return ProductPrice(item_code_raw=item_code_raw, price=Decimal(value), price_raw=value)
