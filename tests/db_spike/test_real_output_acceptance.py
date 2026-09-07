"""Round 1.5: real collector output acceptance against the corrected
Round 1 Focused DB Spike persistence model.

Gated behind SMARTCART_LIVE_DB_SPIKE_ACCEPTANCE=1 (unset by default,
mirroring the existing SMARTCART_LIVE_SHUFERSAL_TESTS-style convention
already used by the collectors' own live integration tests) so the normal
test suite never requires live network access:

    SMARTCART_LIVE_DB_SPIKE_ACCEPTANCE=1 uv run pytest \
        tests/db_spike/test_real_output_acceptance.py -v -s

This makes REAL, bounded network calls to the live Shufersal and Rami
Levy portals, using the existing collector public functions (discovery,
download, transport, parse, validate; session/list_directory for Rami
Levy) in exactly the sequence run.py already uses -- no collector code is
modified or bypassed. It fetches one real Shufersal PriceFull, one real
Rami Levy Standard PriceFull, and one real Rami Levy Online PriceFull
(store "039", per docs/adr/0007), and proves the corrected Round 1
persistence model accepts each without destructive normalization.

collected_at note (Round 1.5 governance): none of the collectors' public
one-shot return contracts currently expose a true acquisition-time
timestamp usable as ArtifactOccurrence.collected_at (see the Collector
Contract Inspection's Fixed Data Invariant 4 discussion). This acceptance
run therefore uses an EXPLICITLY-CONTROLLED, CLEARLY-LABELED test fixture
timestamp (`_acceptance_collected_at()`, captured at this integration
boundary immediately after each download call returns) -- it is a
temporary stand-in for this acceptance check only, not a demonstration
that a production collected_at handoff exists. That handoff remains a
separate, unsolved future integration task.

No raw retailer payload bytes are written to the repository by this test:
everything is fetched fresh from the network each run and discarded after
assertions complete, per Round 1.5's data-provenance/licensing guidance.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pg8000.native
import pytest

from smartcart.collectors.rami_levy import discovery as rl_discovery
from smartcart.collectors.rami_levy import download as rl_download
from smartcart.collectors.rami_levy import parse as rl_parse
from smartcart.collectors.rami_levy import transport as rl_transport
from smartcart.collectors.rami_levy import validate as rl_validate
from smartcart.collectors.rami_levy.session import RamiLevySession
from smartcart.collectors.shufersal import discovery as sf_discovery
from smartcart.collectors.shufersal import download as sf_download
from smartcart.collectors.shufersal import parse as sf_parse
from smartcart.collectors.shufersal import transport as sf_transport
from smartcart.collectors.shufersal import validate as sf_validate
from smartcart.db_spike.activation import PriceObservation, current_state, record_price_observation
from smartcart.db_spike.catalog import (
    add_store_source_alias,
    get_or_create_store_by_alias,
    store_source_aliases,
    upsert_chain,
    upsert_chain_product,
    upsert_subchain,
)
from smartcart.db_spike.content import insert_or_get_content
from smartcart.db_spike.occurrence import get_occurrence, insert_occurrence

_LIVE_ENV_VAR = "SMARTCART_LIVE_DB_SPIKE_ACCEPTANCE"

pytestmark = pytest.mark.skipif(
    os.environ.get(_LIVE_ENV_VAR) != "1",
    reason=f"Round 1.5 real-output acceptance is gated behind {_LIVE_ENV_VAR}=1 (live network).",
)


def _acceptance_collected_at() -> datetime:
    """TEMPORARY TEST FIXTURE VALUE ONLY (see module docstring): the
    collectors' current public return contracts expose no true
    acquisition timestamp, so this acceptance run substitutes an
    explicitly-labeled, timezone-aware UTC value captured at this
    integration boundary. This is not a production collected_at source."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class RealSample:
    """Evidence captured from one real collector fetch, for reporting."""

    chain_id: str
    subchain_id: str
    source: str
    canonical_payload: bytes
    content_hash: str
    record_count: int


def _report(sample: RealSample, label: str) -> None:
    print(f"\n--- {label} ---")
    print(f"chain_id={sample.chain_id} subchain_id={sample.subchain_id} source={sample.source}")
    print(f"canonical payload size: {len(sample.canonical_payload)} bytes")
    print(f"content_hash (sha256): {sample.content_hash}")
    print(f"record_count: {sample.record_count}")


@pytest.fixture(scope="module")
def rami_levy_session_and_listing() -> Iterator[tuple[RamiLevySession, list[dict[str, object]]]]:
    session = RamiLevySession()
    session.login()
    rows = session.list_directory()
    yield session, rows


def test_shufersal_real_pricefull_sample(db_conn: pg8000.native.Connection) -> None:
    # --- A. Canonical payload: exactly what run.py itself does internally,
    # up to the point transport.decompress() returns -- nothing added. ---
    discovered_stores = sf_discovery.discover_stores_file()
    stores_body = sf_download.download_bytes(discovered_stores)
    stores_canonical = sf_transport.decompress(stores_body)
    stores = sf_parse.parse_stores_xml(stores_canonical)
    assert stores, "Shufersal Stores file returned zero stores; cannot pick a real store_id."

    real_store_id = stores[0].store_id
    chain_id = stores[0].chain_id
    subchain_id = stores[0].subchain_id

    discovered_pf = sf_discovery.discover_pricefull_file(real_store_id)
    pf_body = sf_download.download_bytes(discovered_pf)
    canonical_payload = sf_transport.decompress(pf_body)
    items = sf_parse.parse_pricefull_xml(canonical_payload)
    collected_at = _acceptance_collected_at()

    content_hash = hashlib.sha256(canonical_payload).hexdigest()
    sample = RealSample(
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="shufersal",
        canonical_payload=canonical_payload,
        content_hash=content_hash,
        record_count=len(items),
    )
    _report(sample, "SHUFERSAL real PriceFull")

    assert len(canonical_payload) > 0
    assert items, "Shufersal PriceFull file returned zero items; cannot validate record shape."

    validation = sf_validate.validate_pricefull(items, source_filename=discovered_pf.filename)
    print(f"validation.hard_failed={validation.hard_failed} warnings={validation.warnings}")

    # --- B/C. Persistence: Content -> Store identity -> Occurrence ---
    upsert_chain(db_conn, chain_id=chain_id, chain_name=stores[0].chain_name)
    upsert_subchain(db_conn, chain_id=chain_id, subchain_id=subchain_id, subchain_name=None)

    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="shufersal",
        alias_context="filename_and_xml_store_id",
        raw_value=real_store_id,
        store_name=stores[0].store_name,
    )

    content = insert_or_get_content(db_conn, canonical_payload)
    assert content.content_hash == content_hash
    assert content.payload_size_bytes == len(canonical_payload)

    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=chain_id,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename=discovered_pf.filename,
        schema_family=None,
        collected_at=collected_at,
        validation_status="validation_failed" if validation.hard_failed else "valid",
        validation_detail={
            "warnings": validation.warnings,
            "hard_fail_reasons": validation.hard_fail_reasons,
        },
    )
    row = get_occurrence(db_conn, occurrence.occurrence_id)
    assert row is not None
    assert row["chain_id"] == chain_id
    assert row["store_id"] == store_id
    assert row["collected_at"] == collected_at
    assert row["content_id"] == content.content_id

    # --- E. Derived shape: one real valid item -> ChainProduct/CurrentState/PriceHistory ---
    real_item = next(
        (
            i
            for i in items
            if i.item_price is not None and _is_decimal(i.item_price) and i.item_code
        ),
        None,
    )
    assert real_item is not None, (
        "No item with a decimal-shaped ItemPrice found in the real sample."
    )
    assert (
        real_item.item_price is not None
    )  # narrows for mypy; already guaranteed by the filter above

    upsert_chain_product(db_conn, chain_id=chain_id, item_code_raw=real_item.item_code)
    price_history_id = record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=chain_id,
            store_id=store_id,
            item_code_raw=real_item.item_code,
            price=Decimal(real_item.item_price),
            price_raw=real_item.item_price,
            observed_at=collected_at,
            source_occurrence_id=occurrence.occurrence_id,
        ),
    )
    assert price_history_id > 0
    state = current_state(
        db_conn, chain_id=chain_id, store_id=store_id, item_code_raw=real_item.item_code
    )
    assert state is not None
    assert state["current_price"] == Decimal(real_item.item_price)
    assert state["current_price_raw"] == real_item.item_price
    print(
        f"derived: item_code_raw={real_item.item_code!r} price_raw={real_item.item_price!r} "
        f"typed={state['current_price']!r}"
    )


def test_rami_levy_standard_real_pricefull_sample(
    db_conn: pg8000.native.Connection,
    rami_levy_session_and_listing: tuple[RamiLevySession, list[dict[str, object]]],
) -> None:
    session, rows = rami_levy_session_and_listing

    discovered_stores = rl_discovery.find_stores_file(rows)
    stores_body = rl_download.download_bytes(session, discovered_stores.filename)
    stores_canonical = rl_transport.normalize(stores_body)
    stores = rl_parse.parse_stores_xml(stores_canonical)
    assert stores, "Rami Levy Stores file returned zero stores; cannot pick a real store_id."

    standard_store = next((s for s in stores if s.store_id != "039"), None)
    assert standard_store is not None, (
        "No non-039 (standard-family) store found in real Stores file."
    )
    real_store_id = standard_store.store_id
    chain_id = standard_store.chain_id
    subchain_id = standard_store.subchain_id

    discovered_pf = rl_discovery.find_pricefull_file(rows, real_store_id)
    pf_body = rl_download.download_bytes(session, discovered_pf.filename)
    canonical_payload = rl_transport.normalize(pf_body)
    items = rl_parse.parse_pricefull_xml(canonical_payload)
    collected_at = _acceptance_collected_at()

    assert rl_parse.schema_family_of(items) == "standard"

    content_hash = hashlib.sha256(canonical_payload).hexdigest()
    sample = RealSample(
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="rami_levy",
        canonical_payload=canonical_payload,
        content_hash=content_hash,
        record_count=len(items),
    )
    _report(sample, "RAMI LEVY STANDARD real PriceFull")

    assert len(canonical_payload) > 0
    assert items, "Rami Levy standard PriceFull file returned zero items."

    validation = rl_validate.validate_pricefull(items, source_filename=discovered_pf.filename)
    print(f"validation.hard_failed={validation.hard_failed} warnings={validation.warnings}")

    upsert_chain(db_conn, chain_id=chain_id, chain_name=standard_store.chain_name)
    upsert_subchain(db_conn, chain_id=chain_id, subchain_id=subchain_id, subchain_name=None)

    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="rami_levy",
        alias_context="filename_and_xml_store_id",
        raw_value=real_store_id,
        store_name=standard_store.store_name,
    )

    content = insert_or_get_content(db_conn, canonical_payload)
    assert content.content_hash == content_hash

    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=chain_id,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename=discovered_pf.filename,
        schema_family="standard",
        collected_at=collected_at,
        validation_status="validation_failed" if validation.hard_failed else "valid",
        validation_detail={
            "warnings": validation.warnings,
            "hard_fail_reasons": validation.hard_fail_reasons,
        },
    )
    row = get_occurrence(db_conn, occurrence.occurrence_id)
    assert row is not None
    assert row["schema_family"] == "standard"
    assert row["store_id"] == store_id

    real_item = next(
        (
            i
            for i in items
            if i.item_price is not None and _is_decimal(i.item_price) and i.item_code
        ),
        None,
    )
    assert real_item is not None, (
        "No item with a decimal-shaped ItemPrice found in the real sample."
    )
    assert (
        real_item.item_price is not None
    )  # narrows for mypy; already guaranteed by the filter above

    upsert_chain_product(db_conn, chain_id=chain_id, item_code_raw=real_item.item_code)
    record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=chain_id,
            store_id=store_id,
            item_code_raw=real_item.item_code,
            price=Decimal(real_item.item_price),
            price_raw=real_item.item_price,
            observed_at=collected_at,
            source_occurrence_id=occurrence.occurrence_id,
        ),
    )
    state = current_state(
        db_conn, chain_id=chain_id, store_id=store_id, item_code_raw=real_item.item_code
    )
    assert state is not None
    assert state["current_price"] == Decimal(real_item.item_price)
    print(f"derived: item_code_raw={real_item.item_code!r} price_raw={real_item.item_price!r}")


def test_rami_levy_online_real_pricefull_sample(
    db_conn: pg8000.native.Connection,
    rami_levy_session_and_listing: tuple[RamiLevySession, list[dict[str, object]]],
) -> None:
    session, rows = rami_levy_session_and_listing
    online_filename_token = "039"

    discovered_stores = rl_discovery.find_stores_file(rows)
    stores_body = rl_download.download_bytes(session, discovered_stores.filename)
    stores_canonical = rl_transport.normalize(stores_body)
    stores = rl_parse.parse_stores_xml(stores_canonical)
    online_store = next((s for s in stores if s.store_id == online_filename_token), None)
    assert online_store is not None, "Store '039' not found in real Stores file."
    chain_id = online_store.chain_id
    subchain_id = online_store.subchain_id

    discovered_pf = rl_discovery.find_pricefull_file(rows, online_filename_token)
    pf_body = rl_download.download_bytes(session, discovered_pf.filename)
    canonical_payload = rl_transport.normalize(pf_body)
    items = rl_parse.parse_pricefull_xml(canonical_payload)
    collected_at = _acceptance_collected_at()

    assert rl_parse.schema_family_of(items) == "online"

    content_hash = hashlib.sha256(canonical_payload).hexdigest()
    sample = RealSample(
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="rami_levy",
        canonical_payload=canonical_payload,
        content_hash=content_hash,
        record_count=len(items),
    )
    _report(sample, "RAMI LEVY ONLINE real PriceFull (store 039)")

    assert len(canonical_payload) > 0
    assert items, "Rami Levy online PriceFull file returned zero items."

    xml_store_id = items[0].store_id  # observed unpadded, e.g. "39"
    print(f"filename/catalog token={online_filename_token!r} XML-carried store_id={xml_store_id!r}")

    validation = rl_validate.validate_pricefull(items, source_filename=discovered_pf.filename)
    print(f"validation.hard_failed={validation.hard_failed} warnings={validation.warnings}")
    print(f"validation.ids_matched={validation.ids_matched} (family-scoped 039/39 equivalence)")

    upsert_chain(db_conn, chain_id=chain_id, chain_name=online_store.chain_name)
    upsert_subchain(db_conn, chain_id=chain_id, subchain_id=subchain_id, subchain_name=None)

    # D. Store identity: resolve/create via the filename/catalog token
    # first, then register the XML-carried value as a SECOND alias for
    # the SAME store -- neither becomes Store's semantic identity.
    store_id = get_or_create_store_by_alias(
        db_conn,
        chain_id=chain_id,
        subchain_id=subchain_id,
        source="rami_levy",
        alias_context="filename_store_id_online",
        raw_value=online_filename_token,
        store_name=online_store.store_name,
    )
    if xml_store_id != online_filename_token:
        add_store_source_alias(
            db_conn,
            chain_id=chain_id,
            store_id=store_id,
            source="rami_levy",
            alias_context="xml_store_id_online",
            raw_value=xml_store_id,
        )
    aliases = store_source_aliases(db_conn, store_id=store_id)
    print(f"store_source_alias rows for store_id={store_id}: {aliases}")
    alias_raw_values = {raw_value for (_, _, raw_value) in aliases}
    assert online_filename_token in alias_raw_values
    assert xml_store_id in alias_raw_values

    content = insert_or_get_content(db_conn, canonical_payload)
    assert content.content_hash == content_hash

    occurrence = insert_occurrence(
        db_conn,
        content_id=content.content_id,
        ingestion_run_id=None,
        chain_id=chain_id,
        store_id=store_id,
        artifact_kind="pricefull",
        source_filename=discovered_pf.filename,
        schema_family="online",
        collected_at=collected_at,
        validation_status="validation_failed" if validation.hard_failed else "valid",
        validation_detail={
            "warnings": validation.warnings,
            "hard_fail_reasons": validation.hard_fail_reasons,
        },
    )
    row = get_occurrence(db_conn, occurrence.occurrence_id)
    assert row is not None
    assert row["schema_family"] == "online"
    assert row["store_id"] == store_id

    real_item = next(
        (
            i
            for i in items
            if i.item_price is not None and _is_decimal(i.item_price) and i.item_code
        ),
        None,
    )
    assert real_item is not None, (
        "No item with a decimal-shaped ItemPrice found in the real sample."
    )
    assert (
        real_item.item_price is not None
    )  # narrows for mypy; already guaranteed by the filter above

    upsert_chain_product(db_conn, chain_id=chain_id, item_code_raw=real_item.item_code)
    record_price_observation(
        db_conn,
        PriceObservation(
            chain_id=chain_id,
            store_id=store_id,
            item_code_raw=real_item.item_code,
            price=Decimal(real_item.item_price),
            price_raw=real_item.item_price,
            observed_at=collected_at,
            source_occurrence_id=occurrence.occurrence_id,
        ),
    )
    state = current_state(
        db_conn, chain_id=chain_id, store_id=store_id, item_code_raw=real_item.item_code
    )
    assert state is not None
    assert state["current_price"] == Decimal(real_item.item_price)
    print(f"derived: item_code_raw={real_item.item_code!r} price_raw={real_item.item_price!r}")


def _is_decimal(value: str) -> bool:
    try:
        Decimal(value)
    except Exception:
        return False
    return True
