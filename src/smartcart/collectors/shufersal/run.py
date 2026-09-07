"""Orchestration for one Shufersal Phase 1A run.

Wires together discovery -> download -> transport -> parse -> validate for
the Stores file and for each requested store's PriceFull file. A failure
processing one PriceFull file does not stop the others from being
attempted. This is deliberately a couple of plain functions plus a loop,
not a generic pipeline/framework -- appropriate for Phase 1A's single-chain
scope (see docs/adr/0004).

Only the exceptions explicitly modeled by discovery.py/download.py/
transport.py/parse.py are caught here (each maps to one failed_stage).
Truly unexpected exceptions are intentionally not swallowed, since doing so
would hide real bugs rather than record an expected per-file failure mode.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from smartcart.collectors.shufersal import discovery, download, parse, transport, validate
from smartcart.collectors.shufersal.discovery import DiscoveredFile, DiscoveryError
from smartcart.collectors.shufersal.download import DownloadAuthExpiredError, DownloadError
from smartcart.collectors.shufersal.parse import ParseError
from smartcart.collectors.shufersal.records import (
    FileOutcome,
    RunSummary,
    ShufersalPriceItemRaw,
    ShufersalStoreRaw,
)
from smartcart.collectors.shufersal.transport import TransportError
from smartcart.collectors.shufersal.validate import ValidationOutcome

_MAX_REDISCOVERY_ATTEMPTS_ON_EXPIRED_URL = 1


def _timed[T](fn: Callable[[], T], durations: dict[str, float], stage: str) -> T:
    start = time.monotonic()
    try:
        return fn()
    finally:
        durations[stage] = durations.get(stage, 0.0) + (time.monotonic() - start)


def _download_with_rediscovery(
    initial: DiscoveredFile,
    rediscover: Callable[[], DiscoveredFile],
    durations: dict[str, float],
) -> tuple[bytes, DiscoveredFile]:
    """Download bytes for `initial`. On an expired/auth-invalid signed URL,
    rediscover exactly once and retry with the fresh URL -- never retries
    the same stale URL. Raises DownloadError/DiscoveryError on failure."""
    discovered = initial
    attempts_remaining = _MAX_REDISCOVERY_ATTEMPTS_ON_EXPIRED_URL

    while True:
        start = time.monotonic()
        try:
            body = download.download_bytes(discovered)
        except DownloadAuthExpiredError:
            durations["download"] = durations.get("download", 0.0) + (time.monotonic() - start)
            if attempts_remaining <= 0:
                raise
            attempts_remaining -= 1
            discovered = _timed(rediscover, durations, "discovery")
            continue
        durations["download"] = durations.get("download", 0.0) + (time.monotonic() - start)
        return body, discovered


def _outcome_from_failure(
    file_kind: str,
    discovered: DiscoveredFile | None,
    store_id: str | None,
    failed_stage: str,
    exc: Exception,
    durations: dict[str, float],
) -> FileOutcome:
    return FileOutcome(
        file_kind=file_kind,
        source_filename=discovered.filename if discovered else None,
        store_id=store_id,
        discovered_at=discovered.discovered_at if discovered else None,
        signed_url_expiry_raw=discovered.signed_url_expiry_raw if discovered else None,
        download_completed_at=None,
        compressed_bytes=None,
        decompressed_bytes=None,
        record_count=None,
        succeeded=False,
        failed_stage=failed_stage,
        error_type=type(exc).__name__,
        error_message=str(exc),
        stage_durations_seconds=dict(durations),
    )


def _outcome_from_success(
    *,
    file_kind: str,
    discovered: DiscoveredFile,
    store_id: str | None,
    compressed_bytes: int,
    decompressed_bytes: int,
    record_count: int,
    validation: ValidationOutcome,
    durations: dict[str, float],
) -> FileOutcome:
    return FileOutcome(
        file_kind=file_kind,
        source_filename=discovered.filename,
        store_id=store_id,
        discovered_at=discovered.discovered_at,
        signed_url_expiry_raw=discovered.signed_url_expiry_raw,
        download_completed_at=datetime.now(UTC),
        compressed_bytes=compressed_bytes,
        decompressed_bytes=decompressed_bytes,
        record_count=record_count,
        filename_ids=validation.filename_ids,
        xml_ids=validation.xml_ids,
        ids_matched=validation.ids_matched,
        succeeded=not validation.hard_failed,
        hard_fail_reasons=validation.hard_fail_reasons,
        warnings=validation.warnings,
        failed_stage="validation" if validation.hard_failed else None,
        stage_durations_seconds=dict(durations),
    )


def run_stores() -> tuple[list[ShufersalStoreRaw], FileOutcome]:
    """Discover, download, decompress, parse, and validate the current
    Shufersal Stores file."""
    durations: dict[str, float] = {}
    discovered: DiscoveredFile | None = None

    try:
        discovered = _timed(discovery.discover_stores_file, durations, "discovery")
        body, discovered = _download_with_rediscovery(
            discovered, discovery.discover_stores_file, durations
        )
        decompressed = _timed(lambda: transport.decompress(body), durations, "transport")
        stores = _timed(lambda: parse.parse_stores_xml(decompressed), durations, "parse")
        validation = _timed(lambda: validate.validate_stores(stores), durations, "validation")
    except DiscoveryError as exc:
        return [], _outcome_from_failure("stores", discovered, None, "discovery", exc, durations)
    except DownloadError as exc:
        return [], _outcome_from_failure("stores", discovered, None, "download", exc, durations)
    except TransportError as exc:
        return [], _outcome_from_failure("stores", discovered, None, "transport", exc, durations)
    except ParseError as exc:
        return [], _outcome_from_failure("stores", discovered, None, "parse", exc, durations)

    outcome = _outcome_from_success(
        file_kind="stores",
        discovered=discovered,
        store_id=None,
        compressed_bytes=len(body),
        decompressed_bytes=len(decompressed),
        record_count=len(stores),
        validation=validation,
        durations=durations,
    )
    return stores, outcome


def run_pricefull_for_store(store_id: str) -> tuple[list[ShufersalPriceItemRaw], FileOutcome]:
    """Discover, download, decompress, parse, and validate the current
    Shufersal PriceFull file for one store_id."""
    durations: dict[str, float] = {}
    discovered: DiscoveredFile | None = None

    try:
        discovered = _timed(
            lambda: discovery.discover_pricefull_file(store_id), durations, "discovery"
        )
        body, discovered = _download_with_rediscovery(
            discovered, lambda: discovery.discover_pricefull_file(store_id), durations
        )
        decompressed = _timed(lambda: transport.decompress(body), durations, "transport")
        items = _timed(lambda: parse.parse_pricefull_xml(decompressed), durations, "parse")
        filename = discovered.filename
        validation = _timed(
            lambda: validate.validate_pricefull(items, source_filename=filename),
            durations,
            "validation",
        )
    except DiscoveryError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "discovery", exc, durations
        )
    except DownloadError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "download", exc, durations
        )
    except TransportError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "transport", exc, durations
        )
    except ParseError as exc:
        return [], _outcome_from_failure("pricefull", discovered, store_id, "parse", exc, durations)

    outcome = _outcome_from_success(
        file_kind="pricefull",
        discovered=discovered,
        store_id=store_id,
        compressed_bytes=len(body),
        decompressed_bytes=len(decompressed),
        record_count=len(items),
        validation=validation,
        durations=durations,
    )
    return items, outcome


def run_phase1a(
    store_ids: Sequence[str],
) -> tuple[list[ShufersalStoreRaw], dict[str, list[ShufersalPriceItemRaw]], RunSummary]:
    """Run one Phase 1A pass: the Stores file, then each given store_id's
    PriceFull file.

    A failure processing one PriceFull file does not prevent the others
    from being attempted. Returns the Stores payload, a dict of
    store_id -> item payload (only for stores whose file succeeded), and a
    RunSummary containing one FileOutcome per processed file -- the
    RunSummary itself never embeds the (potentially large) payload.
    """
    started_at = datetime.now(UTC)
    outcomes: list[FileOutcome] = []

    stores, stores_outcome = run_stores()
    outcomes.append(stores_outcome)

    pricefull_by_store: dict[str, list[ShufersalPriceItemRaw]] = {}
    for store_id in store_ids:
        items, item_outcome = run_pricefull_for_store(store_id)
        outcomes.append(item_outcome)
        if item_outcome.succeeded:
            pricefull_by_store[store_id] = items

    finished_at = datetime.now(UTC)
    summary = RunSummary(started_at=started_at, finished_at=finished_at, outcomes=outcomes)
    return stores, pricefull_by_store, summary
