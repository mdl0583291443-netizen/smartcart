"""Orchestration for one Rami Levy Phase 1A run.

Two run-level dependencies -- without either of these there are no usable
discovered download targets at all, so failure here aborts the whole run
rather than being represented as a per-file outcome:

- login/session establishment (session.login())
- the shared directory listing (session.list_directory())

Once the listing has been fetched, individual file handling is isolated:
one PriceFull file's discovery/download/transport/parse/validation failure
does not prevent any other requested store's PriceFull file from being
attempted, and is represented as that file's own FileOutcome rather than
raised. This mirrors the Shufersal collector's run.py shape (plain
functions plus a loop, no pipeline framework) without sharing code with
it -- see docs/adr/0004 and docs/adr/0003.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from smartcart.collectors.rami_levy import discovery, download, parse, transport, validate
from smartcart.collectors.rami_levy.discovery import DiscoveredFile, DiscoveryError
from smartcart.collectors.rami_levy.download import DownloadError
from smartcart.collectors.rami_levy.parse import ParseError
from smartcart.collectors.rami_levy.records import (
    FileOutcome,
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
    RamiLevyStoreRaw,
    RunSummary,
)
from smartcart.collectors.rami_levy.session import (
    ListingError,
    LoginError,
    RamiLevySession,
    SessionExpiredError,
)
from smartcart.collectors.rami_levy.transport import TransportError
from smartcart.collectors.rami_levy.validate import ValidationOutcome

# Local type-hint convenience only (a plain Union, not a merged model): a
# PriceFull payload is always ALL-standard or ALL-online, never mixed --
# see parse.schema_family_of().
_PriceFullItems = list[RamiLevyPriceItemRawStandard] | list[RamiLevyPriceItemRawOnline]


def _timed[T](fn: Callable[[], T], durations: dict[str, float], stage: str) -> T:
    start = time.monotonic()
    try:
        return fn()
    finally:
        durations[stage] = durations.get(stage, 0.0) + (time.monotonic() - start)


def _outcome_from_failure(
    file_kind: str,
    discovered: DiscoveredFile | None,
    store_id: str | None,
    failed_stage: str,
    exc: Exception,
    durations: dict[str, float],
    listing_fetched_at: datetime,
) -> FileOutcome:
    return FileOutcome(
        file_kind=file_kind,
        source_filename=discovered.filename if discovered else None,
        store_id=store_id,
        discovered_at=listing_fetched_at if discovered else None,
        download_completed_at=None,
        downloaded_bytes=None,
        normalized_bytes=None,
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
    downloaded_bytes: int,
    normalized_bytes: int,
    record_count: int,
    schema_family: str | None = None,
    validation: ValidationOutcome,
    durations: dict[str, float],
    listing_fetched_at: datetime,
) -> FileOutcome:
    return FileOutcome(
        file_kind=file_kind,
        source_filename=discovered.filename,
        store_id=store_id,
        discovered_at=listing_fetched_at,
        download_completed_at=datetime.now(UTC),
        downloaded_bytes=downloaded_bytes,
        normalized_bytes=normalized_bytes,
        record_count=record_count,
        schema_family=schema_family,
        filename_ids=validation.filename_ids,
        xml_ids=validation.xml_ids,
        ids_matched=validation.ids_matched,
        succeeded=not validation.hard_failed,
        hard_fail_reasons=validation.hard_fail_reasons,
        warnings=validation.warnings,
        failed_stage="validation" if validation.hard_failed else None,
        stage_durations_seconds=dict(durations),
    )


def run_stores(
    session: RamiLevySession,
    rows: Sequence[object],
    listing_fetched_at: datetime,
) -> tuple[list[RamiLevyStoreRaw], FileOutcome]:
    """Locate, download, decompress-if-needed, parse, and validate the
    current Stores file from an already-fetched listing."""
    durations: dict[str, float] = {}
    discovered: DiscoveredFile | None = None

    try:
        discovered = _timed(lambda: discovery.find_stores_file(rows), durations, "discovery")
        filename = discovered.filename
        body = _timed(lambda: download.download_bytes(session, filename), durations, "download")
        normalized = _timed(lambda: transport.normalize(body), durations, "transport")
        stores = _timed(lambda: parse.parse_stores_xml(normalized), durations, "parse")
        validation = _timed(lambda: validate.validate_stores(stores), durations, "validation")
    except DiscoveryError as exc:
        return [], _outcome_from_failure(
            "stores", discovered, None, "discovery", exc, durations, listing_fetched_at
        )
    except (DownloadError, SessionExpiredError, LoginError) as exc:
        return [], _outcome_from_failure(
            "stores", discovered, None, "download", exc, durations, listing_fetched_at
        )
    except TransportError as exc:
        return [], _outcome_from_failure(
            "stores", discovered, None, "transport", exc, durations, listing_fetched_at
        )
    except ParseError as exc:
        return [], _outcome_from_failure(
            "stores", discovered, None, "parse", exc, durations, listing_fetched_at
        )

    outcome = _outcome_from_success(
        file_kind="stores",
        discovered=discovered,
        store_id=None,
        downloaded_bytes=len(body),
        normalized_bytes=len(normalized),
        record_count=len(stores),
        validation=validation,
        durations=durations,
        listing_fetched_at=listing_fetched_at,
    )
    return stores, outcome


def run_pricefull_for_store(
    session: RamiLevySession,
    rows: Sequence[object],
    store_id: str,
    listing_fetched_at: datetime,
) -> tuple[_PriceFullItems, FileOutcome]:
    """Locate, download, transport-normalize, parse, and validate the
    current PriceFull file for one store_id from an already-fetched
    listing. store_id must be passed exactly as the chain represents it
    (zero-padding preserved, e.g. "039").

    The schema family (standard vs. online) is never chosen from store_id
    or from the filename shape -- parse.py alone decides it from the
    actual XML content (see parse.schema_family_of())."""
    durations: dict[str, float] = {}
    discovered: DiscoveredFile | None = None

    try:
        discovered = _timed(
            lambda: discovery.find_pricefull_file(rows, store_id), durations, "discovery"
        )
        filename = discovered.filename
        body = _timed(lambda: download.download_bytes(session, filename), durations, "download")
        normalized = _timed(lambda: transport.normalize(body), durations, "transport")
        items = _timed(lambda: parse.parse_pricefull_xml(normalized), durations, "parse")
        validation = _timed(
            lambda: validate.validate_pricefull(items, source_filename=filename),
            durations,
            "validation",
        )
    except DiscoveryError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "discovery", exc, durations, listing_fetched_at
        )
    except (DownloadError, SessionExpiredError, LoginError) as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "download", exc, durations, listing_fetched_at
        )
    except TransportError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "transport", exc, durations, listing_fetched_at
        )
    except ParseError as exc:
        return [], _outcome_from_failure(
            "pricefull", discovered, store_id, "parse", exc, durations, listing_fetched_at
        )

    outcome = _outcome_from_success(
        file_kind="pricefull",
        discovered=discovered,
        store_id=store_id,
        downloaded_bytes=len(body),
        normalized_bytes=len(normalized),
        record_count=len(items),
        schema_family=parse.schema_family_of(items),
        validation=validation,
        durations=durations,
        listing_fetched_at=listing_fetched_at,
    )
    return items, outcome


def run_phase1a(
    store_ids: Sequence[str],
    base_url: str | None = None,
) -> tuple[list[RamiLevyStoreRaw], dict[str, _PriceFullItems], RunSummary]:
    """Run one Phase 1A pass: login, fetch the shared directory listing
    once, then the Stores file and each given store_id's PriceFull file.

    Login and listing failures are run-level (see module docstring) and
    short-circuit with an empty result. Once the listing is available, a
    failure processing one PriceFull file does not prevent the others.
    """
    started_at = datetime.now(UTC)
    session = RamiLevySession(base_url)

    try:
        session.login()
    except LoginError as exc:
        finished_at = datetime.now(UTC)
        summary = RunSummary(
            started_at=started_at,
            finished_at=finished_at,
            session_established=False,
            relogin_count=session.relogin_count,
            outcomes=[],
            run_level_failure_reason=f"login failed: {exc}",
        )
        return [], {}, summary

    try:
        rows = session.list_directory()
    except (ListingError, SessionExpiredError, LoginError) as exc:
        finished_at = datetime.now(UTC)
        summary = RunSummary(
            started_at=started_at,
            finished_at=finished_at,
            session_established=True,
            relogin_count=session.relogin_count,
            outcomes=[],
            run_level_failure_reason=f"directory listing failed: {exc}",
        )
        return [], {}, summary

    listing_fetched_at = datetime.now(UTC)
    outcomes: list[FileOutcome] = []

    stores, stores_outcome = run_stores(session, rows, listing_fetched_at)
    outcomes.append(stores_outcome)

    pricefull_by_store: dict[str, _PriceFullItems] = {}
    for store_id in store_ids:
        items, item_outcome = run_pricefull_for_store(session, rows, store_id, listing_fetched_at)
        outcomes.append(item_outcome)
        if item_outcome.succeeded:
            pricefull_by_store[store_id] = items

    finished_at = datetime.now(UTC)
    summary = RunSummary(
        started_at=started_at,
        finished_at=finished_at,
        session_established=True,
        relogin_count=session.relogin_count,
        outcomes=outcomes,
    )
    return stores, pricefull_by_store, summary
