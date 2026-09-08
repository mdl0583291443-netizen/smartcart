"""Deterministic cross-process TOCTOU regression tests for the write-once
metadata logic in staging.py (docs/adr/0010).

`CrashSafeStagingStore.stage_raw`/`finalize_canonical` publish metadata
via `_atomic_file.atomic_write_once_bytes`, whose cross-process
create-if-absent guarantee comes from a single atomic `os.link` call --
`link(2)` fails with `FileExistsError` if the target name already exists,
so two processes racing to publish the same path are serialized by the
kernel itself. These tests force the exact publication-race interleaving
deterministically, using real OS processes (never threads -- threads
share one interpreter/GIL and would not exercise a genuine cross-process
race) synchronized via a `multiprocessing.Barrier` planted immediately
before each process's real `os.link` call, so both processes are always
released to attempt publication at the same moment -- never
timing/sleep-based, so the race is exposed on every run, not
probabilistically. The barrier only delays *when* each process is allowed
to call `os.link`; the call itself is never mocked or replaced -- both
processes' real `os.link` syscalls still race for real against the
kernel/filesystem, and which one wins is genuinely up to the OS, not the
test.

Not collector data: raw/canonical payloads here are small literals, since
these tests are purely about the storage layer's cross-process
concurrency invariants, unrelated to collector realism.

Linux/WSL only, matching the rest of this package: uses an explicit
`multiprocessing.get_context("fork")` so each child is a copy-on-write
fork of the already-imported parent interpreter, and the per-child
monkeypatch of the process-wide `os.link` reference lives only in that
child's own post-fork memory -- it never touches the parent process or
the sibling child.
"""

from __future__ import annotations

import hashlib
import multiprocessing
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from smartcart.durability_spike.staging import ConflictingMetadataError, CrashSafeStagingStore

_CTX = multiprocessing.get_context("fork")
_BARRIER_TIMEOUT_SECONDS = 10
_JOIN_TIMEOUT_SECONDS = 10
_QUEUE_GET_TIMEOUT_SECONDS = 5


def _install_link_barrier(barrier: Any) -> None:
    """Patch the process-wide `os.link` reference so the REAL `os.link`
    call inside `atomic_write_once_bytes` -- the actual publication
    boundary -- rendezvous with the sibling process at `barrier`
    immediately before being allowed to execute, instead of relying on
    real OS scheduling timing. The real `os.link` syscall is still what
    ultimately runs and races for real; only the moment each process is
    permitted to call it is synchronized. Scoped to this forked child's
    own post-fork (copy-on-write) memory -- never touches the parent or
    the sibling process."""
    real_link = os.link

    def barrier_synced_link(src: Any, dst: Any) -> None:
        barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
        real_link(src, dst)

    os.link = barrier_synced_link  # type: ignore[assignment]


def _stage_raw_worker(
    root: str, raw_bytes: bytes, collected_at: datetime, barrier: Any, result_queue: Any
) -> None:
    """Runs in a forked child. See `_install_link_barrier`: the
    deterministic rendezvous happens at the real os.link publication
    boundary inside atomic_write_once_bytes."""
    _install_link_barrier(barrier)

    store = CrashSafeStagingStore(Path(root))
    try:
        evidence = store.stage_raw(raw_bytes, collected_at)
        result_queue.put(("ok", evidence.raw_content_hash, evidence.collected_at))
    except ConflictingMetadataError as exc:
        result_queue.put(("conflict", str(exc)))
    except Exception as exc:  # pragma: no cover - safety net so the parent never hangs
        result_queue.put(("error", repr(exc)))


def _finalize_canonical_worker(
    root: str, raw_content_hash: str, canonical_bytes: bytes, barrier: Any, result_queue: Any
) -> None:
    """Same barrier-synchronization technique as `_stage_raw_worker`."""
    _install_link_barrier(barrier)

    store = CrashSafeStagingStore(Path(root))
    try:
        evidence = store.finalize_canonical(raw_content_hash, extract=lambda _raw: canonical_bytes)
        result_queue.put(("ok", evidence.content_hash))
    except ConflictingMetadataError as exc:
        result_queue.put(("conflict", str(exc)))
    except Exception as exc:  # pragma: no cover - safety net so the parent never hangs
        result_queue.put(("error", repr(exc)))


def _run_two(
    target: Any, args_1: tuple[Any, ...], args_2: tuple[Any, ...]
) -> list[tuple[Any, ...]]:
    barrier = _CTX.Barrier(2)
    result_queue = _CTX.Queue()
    p1 = _CTX.Process(target=target, args=(*args_1, barrier, result_queue))
    p2 = _CTX.Process(target=target, args=(*args_2, barrier, result_queue))
    p1.start()
    p2.start()
    p1.join(timeout=_JOIN_TIMEOUT_SECONDS)
    p2.join(timeout=_JOIN_TIMEOUT_SECONDS)
    assert p1.exitcode == 0, f"P1 did not exit cleanly (exitcode={p1.exitcode})"
    assert p2.exitcode == 0, f"P2 did not exit cleanly (exitcode={p2.exitcode})"
    return [result_queue.get(timeout=_QUEUE_GET_TIMEOUT_SECONDS) for _ in range(2)]


# --- RAW ----------------------------------------------------------------


def test_concurrent_stage_raw_identical_collected_at_is_singly_durable(tmp_path: Path) -> None:
    raw_bytes = b"raw bytes for concurrent stage_raw regression (identical collected_at)"
    collected_at = datetime.now(UTC)

    results = _run_two(
        _stage_raw_worker,
        (str(tmp_path), raw_bytes, collected_at),
        (str(tmp_path), raw_bytes, collected_at),
    )

    outcomes = [r[0] for r in results]
    assert outcomes == ["ok", "ok"], f"expected both to succeed identically, got {results}"

    fresh_store = CrashSafeStagingStore(tmp_path)
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()
    recovered = fresh_store.recover_raw(expected_hash)
    assert recovered is not None
    assert recovered.collected_at == collected_at


def test_concurrent_stage_raw_conflicting_collected_at_forbids_last_writer_wins(
    tmp_path: Path,
) -> None:
    raw_bytes = b"raw bytes for concurrent stage_raw regression (conflicting collected_at)"
    collected_at_1 = datetime.now(UTC)
    collected_at_2 = collected_at_1 + timedelta(hours=1)

    results = _run_two(
        _stage_raw_worker,
        (str(tmp_path), raw_bytes, collected_at_1),
        (str(tmp_path), raw_bytes, collected_at_2),
    )

    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, (
        "required invariant: exactly one process may durably win a conflicting "
        f"collected_at race; got {results}"
    )
    assert outcomes.count("conflict") == 1, (
        "required invariant: the losing process must observe the winning durable "
        "record and raise ConflictingMetadataError -- it must never silently "
        f"succeed with a different collected_at (last-writer-wins); got {results}"
    )

    winner = next(r for r in results if r[0] == "ok")
    fresh_store = CrashSafeStagingStore(tmp_path)
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()
    recovered = fresh_store.recover_raw(expected_hash)
    assert recovered is not None
    assert recovered.collected_at == winner[2]


# --- CANONICAL --------------------------------------------------------------


def test_concurrent_finalize_canonical_identical_result_is_singly_durable(tmp_path: Path) -> None:
    raw_bytes = b"raw bytes for concurrent finalize_canonical regression (identical result)"
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(raw_bytes, datetime.now(UTC))
    canonical_bytes = b"identical canonical payload for both racers"

    results = _run_two(
        _finalize_canonical_worker,
        (str(tmp_path), staged.raw_content_hash, canonical_bytes),
        (str(tmp_path), staged.raw_content_hash, canonical_bytes),
    )

    outcomes = [r[0] for r in results]
    assert outcomes == ["ok", "ok"], f"expected both to succeed identically, got {results}"

    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.content_hash == hashlib.sha256(canonical_bytes).hexdigest()


def test_concurrent_finalize_canonical_conflicting_result_forbids_last_writer_wins(
    tmp_path: Path,
) -> None:
    raw_bytes = b"raw bytes for concurrent finalize_canonical regression (conflicting result)"
    store = CrashSafeStagingStore(tmp_path)
    staged = store.stage_raw(raw_bytes, datetime.now(UTC))
    canonical_bytes_a = b"canonical payload A"
    canonical_bytes_b = b"canonical payload B"

    results = _run_two(
        _finalize_canonical_worker,
        (str(tmp_path), staged.raw_content_hash, canonical_bytes_a),
        (str(tmp_path), staged.raw_content_hash, canonical_bytes_b),
    )

    outcomes = [r[0] for r in results]
    assert outcomes.count("ok") == 1, (
        "required invariant: exactly one process may durably win a conflicting "
        f"canonical-result race; got {results}"
    )
    assert outcomes.count("conflict") == 1, (
        "required invariant: the losing process must observe the winning durable "
        "canonical record and raise ConflictingMetadataError -- it must never "
        f"silently repoint canonical metadata (last-writer-wins); got {results}"
    )

    winner = next(r for r in results if r[0] == "ok")
    fresh_store = CrashSafeStagingStore(tmp_path)
    recovered = fresh_store.recover_canonical(staged.raw_content_hash)
    assert recovered is not None
    assert recovered.content_hash == winner[1]
