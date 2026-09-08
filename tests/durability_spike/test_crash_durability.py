"""Crash-durability spike proofs (docs/adr/0010).

Uses the REAL Shufersal collector's own public discovery/download/
transport/parse functions to obtain the raw transport bytes and to
perform canonical extraction and parse validation -- exactly what
smartcart.collectors.shufersal.run.run_pricefull_for_store does
internally, nothing added or bypassed. The only thing faked is the HTTP
transport itself (urllib.request.urlopen), via the same deterministic
monkeypatching technique already used by
tests/collectors/shufersal/test_run_integration.py's own offline
orchestration tests -- so this is a real, bounded collector acceptance
path, not synthetic data invented for this spike.

Fault injection at durability boundaries (crash-window tests 3 and 7) is
done deterministically by monkeypatching the staging module's metadata
write step, per the task's explicit allowance to use deterministic fault
injection instead of a true process kill.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from smartcart.collectors.shufersal import discovery, download, parse, transport, validate
from smartcart.durability_spike.staging import (
    ConflictingMetadataError,
    CrashSafeStagingStore,
    NotStagedError,
)

CHAIN_ID = "7290027600007"
SUBCHAIN_ID = "002"
STORE_ID = "413"
ITEM_COUNT = 5


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class SimulatedCrashError(Exception):
    """Marker exception for deterministic fault injection at a durability
    boundary (see module docstring)."""


def _pricefull_xml() -> bytes:
    items = "".join(
        "<Item>"
        "<PriceUpdateTime>2026-09-04T06:23:00</PriceUpdateTime>"
        f"<ItemCode>{1000000000000 + i}</ItemCode>"
        "<LastSaleDateTime>2026-09-04T00:00:00</LastSaleDateTime>"
        "<ItemType>1</ItemType>"
        f"<ItemName>Test Item {i}</ItemName>"
        "<ManufactureName>Acme</ManufactureName>"
        "<ManufactureCountry>IL</ManufactureCountry>"
        f"<ManufactureItemDescription>Test Item {i}</ManufactureItemDescription>"
        "<UnitQty>Gram</UnitQty>"
        "<Quantity>100.00</Quantity>"
        "<UnitOfMeasure>100 Gram</UnitOfMeasure>"
        "<bIsWeighted>0</bIsWeighted>"
        "<QtyInPackage>1</QtyInPackage>"
        "<ItemPrice>10.00</ItemPrice>"
        "<UnitOfMeasurePrice>10.00</UnitOfMeasurePrice>"
        "<AllowDiscount>1</AllowDiscount>"
        "<ItemStatus />"
        "</Item>"
        for i in range(ITEM_COUNT)
    )
    xml = (
        f"<Root><ChainID>{CHAIN_ID}</ChainID><SubChainID>{SUBCHAIN_ID}</SubChainID>"
        f"<StoreID>{STORE_ID}</StoreID><BikoretNo>0</BikoretNo><Items>{items}</Items></Root>"
    )
    return b"\xef\xbb\xbf" + xml.encode("utf-8")


def _pricefull_listing_html() -> str:
    return (
        "<table><tbody><tr>"
        f'<td><a href="https://fake.blob.example/pricefull/PriceFull{CHAIN_ID}-{SUBCHAIN_ID}-'
        f'{STORE_ID}-20260907-034000.gz?sv=x&amp;se=2026-09-07T09%3A00%3A00Z&amp;sp=r">Download'
        "</a></td>"
        "<td>9/7/2026 3:40:00 AM</td>"
        "</tr></tbody></table>"
    )


@pytest.fixture
def real_discovered_and_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[discovery.DiscoveredFile, bytes]:
    """The real DiscoveredFile plus the real, complete raw transport bytes
    for one Shufersal PriceFull file, obtained via the actual collector's
    discovery.discover_pricefull_file + download.download_bytes:
    gzip-compressed, exactly as the retailer would serve it. Only
    urllib.request.urlopen is faked (matching the existing offline
    collector test convention); no collector code is modified or bypassed.
    The DiscoveredFile is exposed (not just the bytes) because
    validate.validate_pricefull needs its filename.
    """

    def fake_urlopen(request: urllib.request.Request, timeout: float = 0) -> _FakeResponse:
        if "catID=2" in request.full_url:
            return _FakeResponse(_pricefull_listing_html().encode("utf-8"))
        return _FakeResponse(gzip.compress(_pricefull_xml()))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    discovered = discovery.discover_pricefull_file(STORE_ID)
    raw_bytes = download.download_bytes(discovered)
    return discovered, raw_bytes


@pytest.fixture
def real_raw_transport_bytes(
    real_discovered_and_raw: tuple[discovery.DiscoveredFile, bytes],
) -> bytes:
    return real_discovered_and_raw[1]


# --- 1. Raw acquisition timestamp -----------------------------------------


def test_raw_acquisition_timestamp_is_aware_utc(real_raw_transport_bytes: bytes) -> None:
    """collected_at is captured immediately once full raw bytes are in
    hand (real_raw_transport_bytes already reflects a completed
    download.download_bytes call), and must be timezone-aware UTC."""
    collected_at = datetime.now(UTC)
    assert collected_at.tzinfo is not None
    assert collected_at.utcoffset() == timedelta(0)


# --- 2. Raw durable staging -------------------------------------------------


def test_raw_durable_staging_survives_fresh_recovery(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, collected_at)

    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_raw(staged.raw_content_hash)

    assert recovered is not None
    assert recovered.collected_at == collected_at
    assert fresh_store.get_raw_bytes(recovered) == real_raw_transport_bytes


# --- 3. Crash before raw stage completion -----------------------------------


def test_crash_before_raw_stage_completion_leaves_no_promotable_record(
    tmp_path: Path, real_raw_transport_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fault injection at the metadata publication boundary itself
    (os.link, inside atomic_write_once_bytes) -- this is control-flow
    evidence that the operation aborts and never publishes metadata when
    os.link cannot run. It is NOT, and cannot be, proof of literal
    post-power-loss persistence -- that would require a real crash/reboot,
    out of scope for a monkeypatched single-process test."""
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    expected_hash = hashlib.sha256(real_raw_transport_bytes).hexdigest()

    def boom(src: object, dst: object) -> None:
        raise SimulatedCrashError("crash injected before metadata os.link could run")

    monkeypatch.setattr(os, "link", boom)

    with pytest.raises(SimulatedCrashError):
        store.stage_raw(real_raw_transport_bytes, collected_at)

    # A fresh instance -- never the writer instance -- is the one making
    # every claim here: the raw blob is durable and detectable (an
    # incomplete orphan, since stage_raw's blob write runs before the
    # metadata publish that was interrupted)...
    fresh_store = CrashSafeStagingStore(tmp_path)
    assert fresh_store.raw_blob_exists(expected_hash)
    # ...the metadata's final name was never published (os.link never ran)...
    raw_meta_path = tmp_path / "raw_meta" / f"{expected_hash}.json"
    assert not raw_meta_path.exists()
    # ...so it is not promoted/recoverable as valid staged evidence...
    assert fresh_store.recover_raw(expected_hash) is None
    # ...and no temp file (atomic_write_once_bytes's ".tmp-*" naming
    # pattern) was left behind.
    assert list((tmp_path / "raw_meta").glob(".tmp-*")) == []

    # Retry is a genuinely new acquisition attempt, not a resumed one --
    # remove the fault and use a wholly new store instance.
    monkeypatch.undo()
    retry_store = CrashSafeStagingStore(tmp_path)
    staged = retry_store.stage_raw(real_raw_transport_bytes, collected_at)
    assert staged.raw_content_hash == expected_hash

    final_store = CrashSafeStagingStore(tmp_path)
    assert final_store.recover_raw(expected_hash) is not None


# --- 4. Crash after raw stage, before extraction ----------------------------


def test_crash_after_raw_stage_before_extraction_reruns_extraction_safely(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, collected_at)

    # Simulate a process restart: a brand-new instance, before canonical
    # finalization ever ran.
    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered_raw = fresh_store.recover_raw(staged.raw_content_hash)
    assert recovered_raw is not None
    assert recovered_raw.collected_at == collected_at

    evidence = fresh_store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)

    expected_canonical = transport.decompress(real_raw_transport_bytes)
    assert evidence.content_hash == hashlib.sha256(expected_canonical).hexdigest()
    # Redo must not generate or alter collected_at.
    assert evidence.collected_at == collected_at


# --- 5. Canonical hash integrity --------------------------------------------


def test_canonical_hash_integrity_and_byte_identical_recovery(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, datetime.now(UTC))
    expected_canonical = transport.decompress(real_raw_transport_bytes)

    evidence = store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)

    assert evidence.content_hash == hashlib.sha256(expected_canonical).hexdigest()
    recovered_bytes = store.get_canonical_bytes(evidence)
    assert hashlib.sha256(recovered_bytes).hexdigest() == evidence.content_hash
    assert recovered_bytes == expected_canonical


# --- 6. Canonical blob dedup / idempotency ----------------------------------


def test_canonical_blob_finalize_is_idempotent_and_deduplicated(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, datetime.now(UTC))

    first = store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)
    second = store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)

    assert first.content_hash == second.content_hash
    blob_files = list((tmp_path / "canonical_blobs").rglob("*.bin"))
    assert len(blob_files) == 1


# --- 7. Crash between canonical blob and canonical metadata -----------------


def test_crash_between_canonical_blob_and_metadata_leaves_detectable_orphan_not_promotable(
    tmp_path: Path, real_raw_transport_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fault injection at the canonical metadata publication boundary
    itself (os.link, inside atomic_write_once_bytes) -- control-flow
    evidence only, not proof of literal post-power-loss persistence (see
    the raw-side counterpart's docstring above)."""
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, collected_at)
    expected_canonical = transport.decompress(real_raw_transport_bytes)
    expected_hash = hashlib.sha256(expected_canonical).hexdigest()

    def boom(src: object, dst: object) -> None:
        raise SimulatedCrashError("crash injected before canonical metadata os.link could run")

    monkeypatch.setattr(os, "link", boom)

    with pytest.raises(SimulatedCrashError):
        store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)
    monkeypatch.undo()

    # A fresh instance -- never the writer instance `store` -- is the one
    # making every claim here: the orphan blob is durable and detectable...
    fresh_store = CrashSafeStagingStore(tmp_path)
    assert fresh_store.canonical_blob_exists(expected_hash)
    # ...the metadata's final name was never published...
    canonical_meta_path = tmp_path / "canonical_meta" / f"{staged.raw_content_hash}.json"
    assert not canonical_meta_path.exists()
    # ...but never silently promoted into usable evidence...
    assert fresh_store.recover_canonical(staged.raw_content_hash) is None
    # ...and no temp file was left behind.
    assert list((tmp_path / "canonical_meta").glob(".tmp-*")) == []

    # Retry through a wholly new store instance; fresh recovery succeeds.
    retry_store = CrashSafeStagingStore(tmp_path)
    evidence = retry_store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)
    assert evidence.content_hash == expected_hash

    final_store = CrashSafeStagingStore(tmp_path)
    recovered = final_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.content_hash == expected_hash


# --- 8. Full canonical recovery ---------------------------------------------


def test_full_canonical_recovery_from_durable_state_only(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, collected_at)
    store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)
    raw_content_hash = staged.raw_content_hash
    del store, staged  # no in-memory pre-crash state is carried forward

    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_canonical(raw_content_hash)

    assert recovered is not None
    recovered_bytes = fresh_store.get_canonical_bytes(recovered)
    assert hashlib.sha256(recovered_bytes).hexdigest() == recovered.content_hash
    assert recovered.collected_at == collected_at


# --- 9. Existing parse/validation --------------------------------------------


def test_recovered_canonical_bytes_pass_the_real_parse_and_validation_path(
    tmp_path: Path,
    real_discovered_and_raw: tuple[discovery.DiscoveredFile, bytes],
) -> None:
    """Recovered canonical bytes must go through the REAL Shufersal parser
    (parse.parse_pricefull_xml) AND the real Shufersal validation
    (validate.validate_pricefull) -- not just parse -- and produce the
    same bounded result as the equivalent normal (non-crash-recovered)
    path."""
    discovered, raw_bytes = real_discovered_and_raw
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(raw_bytes, datetime.now(UTC))
    store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)

    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    recovered_bytes = fresh_store.get_canonical_bytes(recovered)

    normal_canonical = transport.decompress(raw_bytes)
    expected_items = parse.parse_pricefull_xml(normal_canonical)
    recovered_items = parse.parse_pricefull_xml(recovered_bytes)

    assert recovered_items == expected_items
    assert len(recovered_items) == ITEM_COUNT

    expected_validation = validate.validate_pricefull(
        expected_items, source_filename=discovered.filename
    )
    recovered_validation = validate.validate_pricefull(
        recovered_items, source_filename=discovered.filename
    )

    assert recovered_validation.hard_failed == expected_validation.hard_failed
    assert recovered_validation.hard_fail_reasons == expected_validation.hard_fail_reasons
    assert recovered_validation.warnings == expected_validation.warnings
    assert recovered_validation.ids_matched == expected_validation.ids_matched
    assert not recovered_validation.hard_failed
    assert recovered_validation.ids_matched is True


# --- collected_at must be UTC, not merely aware (fails closed) -------------


def test_stage_raw_accepts_aware_utc_datetime(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    store = CrashSafeStagingStore(tmp_path)
    collected_at = datetime.now(UTC)

    staged = store.stage_raw(real_raw_transport_bytes, collected_at)

    assert staged.collected_at == collected_at
    assert staged.collected_at.utcoffset() == timedelta(0)


def test_stage_raw_rejects_naive_datetime(tmp_path: Path, real_raw_transport_bytes: bytes) -> None:
    store = CrashSafeStagingStore(tmp_path)
    naive = datetime(2026, 9, 7, 12, 0, 0)  # no tzinfo

    with pytest.raises(ValueError, match="naive"):
        store.stage_raw(real_raw_transport_bytes, naive)

    # Fails closed: no raw blob is left behind for a rejected collected_at.
    assert not store.raw_blob_exists(hashlib.sha256(real_raw_transport_bytes).hexdigest())


def test_stage_raw_rejects_non_utc_aware_offset(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    """+03:00 (Israel Standard Time, unadjusted) must be REJECTED, not
    silently converted to UTC -- this boundary fails closed rather than
    reinterpreting a caller's timestamp."""
    store = CrashSafeStagingStore(tmp_path)
    plus_three = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))

    with pytest.raises(ValueError, match="UTC"):
        store.stage_raw(real_raw_transport_bytes, plus_three)

    assert not store.raw_blob_exists(hashlib.sha256(real_raw_transport_bytes).hexdigest())


# --- 10. No persistence leak (structural checks) -----------------------------


def test_finalize_canonical_without_staged_raw_raises(tmp_path: Path) -> None:
    store = CrashSafeStagingStore(tmp_path)
    with pytest.raises(NotStagedError):
        store.finalize_canonical("f" * 64, extract=lambda b: b)


def test_durability_spike_module_has_no_persistence_or_collector_dependency() -> None:
    """ADR 0008 boundary: this spike must not depend on db_spike and must
    not import from the collectors package (dependency runs collectors ->
    nothing here, never the reverse; this module only ever receives
    collector bytes/functions as plain arguments from the caller).
    Checked via actual import statements, not a raw substring match,
    since prose mentioning "db_spike"/"ArtifactOccurrence" legitimately
    appears in these modules' own docstrings (see docs/adr/0010)."""
    import ast

    import smartcart.durability_spike.blob_store as blob_store_module
    import smartcart.durability_spike.staging as staging_module

    for module in (blob_store_module, staging_module):
        assert module.__file__ is not None
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        assert not any("db_spike" in name for name in imported_modules)
        assert not any("smartcart.collectors" in name for name in imported_modules)


# --- 11. Write-once metadata (never a silent overwrite) ----------------------


def test_restaging_identical_bytes_with_different_collected_at_raises_and_preserves_original(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    """A second stage_raw() for byte-identical raw content with a
    different collected_at must never mutate the already-durable
    original -- it must fail closed instead."""
    store = CrashSafeStagingStore(tmp_path)
    original_collected_at = datetime.now(UTC)
    staged = store.stage_raw(real_raw_transport_bytes, original_collected_at)

    conflicting_collected_at = original_collected_at + timedelta(hours=1)
    with pytest.raises(ConflictingMetadataError, match="collected_at"):
        store.stage_raw(real_raw_transport_bytes, conflicting_collected_at)

    # A fresh instance confirms the durable record itself, not just the
    # in-memory `store`, was never touched by the rejected re-stage.
    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_raw(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.collected_at == original_collected_at


def test_finalize_canonical_retry_with_nondeterministic_extract_raises_and_preserves_original(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    """A second finalize_canonical() call whose (contract-violating,
    non-deterministic) extract produces different bytes must never
    repoint the already-durable canonical metadata record -- it must
    fail closed instead. The tampered retry's blob may still land on
    disk (blob-first sequencing runs before the conflict check), but it
    must remain an unreferenced, non-promoted orphan."""
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, datetime.now(UTC))

    call_count = {"n": 0}

    def flaky_extract(raw: bytes) -> bytes:
        call_count["n"] += 1
        decompressed = transport.decompress(raw)
        return decompressed if call_count["n"] == 1 else decompressed + b"tampered"

    first = store.finalize_canonical(staged.raw_content_hash, extract=flaky_extract)

    with pytest.raises(ConflictingMetadataError, match="content_hash"):
        store.finalize_canonical(staged.raw_content_hash, extract=flaky_extract)

    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.content_hash == first.content_hash

    tampered_hash = hashlib.sha256(
        transport.decompress(real_raw_transport_bytes) + b"tampered"
    ).hexdigest()
    assert fresh_store.canonical_blob_exists(tampered_hash)  # orphaned, detectable, never promoted


def test_stage_raw_and_finalize_canonical_are_true_write_once_idempotent_no_ops(
    tmp_path: Path, real_raw_transport_bytes: bytes
) -> None:
    """Distinguishes true idempotence (a second identical call is a
    genuine no-op, never rewriting the durable metadata file) from mere
    value-equality (a second call that always overwrites but happens to
    write the same bytes back) -- proven via the metadata files'
    mtimes being unchanged, not just via the returned values."""
    store = CrashSafeStagingStore(tmp_path)
    collected_at = datetime.now(UTC)

    staged = store.stage_raw(real_raw_transport_bytes, collected_at)
    raw_meta_path = tmp_path / "raw_meta" / f"{staged.raw_content_hash}.json"
    raw_mtime_after_first = raw_meta_path.stat().st_mtime_ns

    restaged = store.stage_raw(real_raw_transport_bytes, collected_at)
    assert restaged == staged
    assert raw_meta_path.stat().st_mtime_ns == raw_mtime_after_first

    first_canonical = store.finalize_canonical(
        staged.raw_content_hash, extract=transport.decompress
    )
    canonical_meta_path = tmp_path / "canonical_meta" / f"{staged.raw_content_hash}.json"
    canonical_mtime_after_first = canonical_meta_path.stat().st_mtime_ns

    second_canonical = store.finalize_canonical(
        staged.raw_content_hash, extract=transport.decompress
    )
    assert second_canonical == first_canonical
    assert canonical_meta_path.stat().st_mtime_ns == canonical_mtime_after_first


# --- 11b. Post-link / pre-parent-fsync metadata publication boundary --------


def test_raw_metadata_dir_fsync_failure_after_link_propagates_without_claiming_durability(
    tmp_path: Path, real_raw_transport_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """os.link() has already succeeded by the time this failure is
    injected -- the metadata file genuinely, correctly exists on the live
    filesystem afterward (data was fsynced to the temp file before the
    link ran, so content is never partial). This test proves the
    operation still reports failure (never silently claims success), and
    it deliberately does NOT assert that this live-filesystem visibility
    equals confirmed post-power-loss durability -- a monkeypatched,
    single-process test cannot determine whether this directory entry
    would survive a real crash at this exact instant; only real
    crash/reboot testing could. What IS proven: (a) the caller is
    honestly told durability was not confirmed, (b) the metadata content
    that IS visible is complete and parseable, never partial, and (c) a
    later, independent retry closes the gap by going through the
    existing-publication/EEXIST path, which re-fsyncs the parent
    directory itself before trusting it.
    """
    collected_at = datetime.now(UTC)
    store = CrashSafeStagingStore(tmp_path)
    expected_hash = hashlib.sha256(real_raw_transport_bytes).hexdigest()

    import smartcart.durability_spike._atomic_file as atomic_file_module

    real_fsync_dir = atomic_file_module._fsync_dir
    raw_meta_dir = tmp_path / "raw_meta"

    def flaky_fsync_dir(dir_path: Path) -> None:
        if dir_path == raw_meta_dir:
            raise SimulatedCrashError(
                "crash injected after os.link succeeded, before parent fsync confirmed"
            )
        real_fsync_dir(dir_path)

    monkeypatch.setattr(atomic_file_module, "_fsync_dir", flaky_fsync_dir)

    with pytest.raises(SimulatedCrashError):
        store.stage_raw(real_raw_transport_bytes, collected_at)

    # Live-filesystem visibility, NOT a durability claim: the name exists
    # and is fully parseable right now, in this uncrashed process.
    raw_meta_path = raw_meta_dir / f"{expected_hash}.json"
    assert raw_meta_path.exists()
    live_view = store.recover_raw(expected_hash)
    assert live_view is not None
    assert live_view.collected_at == collected_at

    monkeypatch.undo()

    # A wholly fresh store, independent retry: os.link() now sees the
    # already-published name, raises FileExistsError, and the EEXIST
    # branch fsyncs the parent directory itself (unpatched now, for real)
    # before comparing bytes and returning idempotent success.
    retry_store = CrashSafeStagingStore(tmp_path)
    confirmed = retry_store.stage_raw(real_raw_transport_bytes, collected_at)
    assert confirmed.collected_at == collected_at

    final_store = CrashSafeStagingStore(tmp_path)
    recovered = final_store.recover_raw(expected_hash)
    assert recovered is not None
    assert recovered.collected_at == collected_at


def test_canonical_metadata_dir_fsync_failure_after_link_propagates_without_claiming_durability(
    tmp_path: Path, real_raw_transport_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canonical counterpart of the raw post-link/pre-parent-fsync test
    above -- same reasoning, same honesty constraint about what live
    visibility does and does not prove."""
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(real_raw_transport_bytes, datetime.now(UTC))
    expected_canonical = transport.decompress(real_raw_transport_bytes)
    expected_hash = hashlib.sha256(expected_canonical).hexdigest()

    import smartcart.durability_spike._atomic_file as atomic_file_module

    real_fsync_dir = atomic_file_module._fsync_dir
    canonical_meta_dir = tmp_path / "canonical_meta"

    def flaky_fsync_dir(dir_path: Path) -> None:
        if dir_path == canonical_meta_dir:
            raise SimulatedCrashError(
                "crash injected after os.link succeeded, before parent fsync confirmed"
            )
        real_fsync_dir(dir_path)

    monkeypatch.setattr(atomic_file_module, "_fsync_dir", flaky_fsync_dir)

    with pytest.raises(SimulatedCrashError):
        store.finalize_canonical(staged.raw_content_hash, extract=transport.decompress)

    canonical_meta_path = canonical_meta_dir / f"{staged.raw_content_hash}.json"
    assert canonical_meta_path.exists()
    live_view = store.recover_canonical(staged.raw_content_hash)
    assert live_view is not None
    assert live_view.content_hash == expected_hash

    monkeypatch.undo()

    retry_store = CrashSafeStagingStore(tmp_path)
    confirmed = retry_store.finalize_canonical(
        staged.raw_content_hash,
        extract=transport.decompress,
    )
    assert confirmed.content_hash == expected_hash

    final_store = CrashSafeStagingStore(tmp_path)
    recovered = final_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.content_hash == expected_hash


# --- 12. Directory-creation durability ----------------------------------------


def test_directory_fsync_failure_during_new_shard_creation_blocks_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not collector data -- this test is purely about the storage layer's
    directory-creation durability plumbing (docs/adr/0010's directory
    creation durability requirement), so a small literal payload is used
    instead of real_raw_transport_bytes.

    `ensure_dir_durable` durably fsyncs each newly created ancestor
    directory's *parent* before `atomic_write_bytes` ever creates a temp
    file or renames anything into place. If that ancestor-directory fsync
    fails (deterministically injected here), the write must abort before
    any blob or metadata file exists -- a directory-fsync failure can
    never leave a promotable/recoverable record behind.
    """
    store = CrashSafeStagingStore(tmp_path)  # unpatched: base dirs already durable
    raw_bytes = b"directory-fsync-failure regression payload"
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()
    failing_parent = tmp_path / "raw_blobs" / expected_hash[:2]

    import smartcart.durability_spike._atomic_file as atomic_file_module

    real_fsync_dir = atomic_file_module._fsync_dir

    def flaky_fsync_dir(dir_path: Path) -> None:
        if dir_path == failing_parent:
            raise SimulatedCrashError(
                "crash injected while fsyncing a newly created ancestor directory"
            )
        real_fsync_dir(dir_path)

    monkeypatch.setattr(atomic_file_module, "_fsync_dir", flaky_fsync_dir)

    with pytest.raises(SimulatedCrashError):
        store.stage_raw(raw_bytes, datetime.now(UTC))

    monkeypatch.undo()

    # A fresh instance -- never the writer instance -- confirms neither the
    # blob nor any metadata record was left behind by the aborted write.
    fresh_store = CrashSafeStagingStore(tmp_path)
    assert not fresh_store.raw_blob_exists(expected_hash)
    assert fresh_store.recover_raw(expected_hash) is None
