"""Deterministic cross-process regression tests for `ensure_dir_durable`
(docs/adr/0010) proving it does NOT currently satisfy its own stated
contract under concurrency.

Required contract: when `ensure_dir_durable(path)` returns successfully,
the calling process must have confirmed the directory entry through its
OWN `fsync(path.parent)` call -- including when a DIFFERENT process is
the one that actually created the directory. Trusting `path.exists()` (or
a caught `FileExistsError`) as proof of durability, without confirming it
oneself, is exactly the class of bug `_fsync_dir` exists to prevent at the
file level (see `atomic_write_once_bytes`'s EEXIST branch, which
correctly re-fsyncs before trusting) -- `ensure_dir_durable` currently
does not apply the same discipline to itself.

Two structurally distinct code paths inside `ensure_dir_durable` can
return without ever calling `_fsync_dir` on behalf of the calling
process:

    if path.exists():        # (F) fast path: never fsyncs, ever
        return
    ...
    try:
        path.mkdir()
    except FileExistsError:  # (E) loser path: returns without fsyncing
        return

Both are proven independently below, using real OS processes (never
threads) and explicit Event-based IPC to force the exact interleaving
deterministically -- never sleeps, never probabilistic timing. In both
tests, the "winning" process (P1) is deliberately kept blocked before its
own `_fsync_dir` call for the entire duration the assertion is checked,
so P1's eventual fsync can never be mistaken for P2 having confirmed
durability itself; whatever is recorded is unambiguously P2's own action.

Both tests are expected to be RED against the current implementation.
"""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
from typing import Any

import pytest

_CTX = multiprocessing.get_context("fork")
_EVENT_TIMEOUT_SECONDS = 10
_JOIN_TIMEOUT_SECONDS = 10
_QUEUE_GET_TIMEOUT_SECONDS = 5


# --- E: FileExistsError loser path ------------------------------------------


def _e_p1_worker(
    path_str: str,
    p2_passed_exists_check: Any,
    p1_mkdir_done: Any,
    release_p1_fsync: Any,
) -> None:
    """P1: wait until P2 has already evaluated `path.exists()` as False
    (so P1 cannot possibly create the directory before P2's own exists
    check runs), then perform a REAL, unpatched `mkdir` -- this process's
    own genuine attempt -- signal completion, then block, deliberately,
    before calling its own `_fsync_dir`, until the test explicitly
    releases it."""
    import smartcart.durability_spike._atomic_file as atomic_file_module

    path = Path(path_str)
    p2_passed_exists_check.wait(timeout=_EVENT_TIMEOUT_SECONDS)
    path.mkdir()
    p1_mkdir_done.set()
    release_p1_fsync.wait(timeout=_EVENT_TIMEOUT_SECONDS)
    atomic_file_module._fsync_dir(path.parent)


def _e_p2_worker(
    path_str: str,
    p2_passed_exists_check: Any,
    p1_mkdir_done: Any,
    p2_fsync_called: Any,
    result_queue: Any,
) -> None:
    """P2: calls the REAL, unmodified `ensure_dir_durable(path)`. Two
    independent, separately-scoped instrumentation points:

    - `os.mkdir` is wrapped so that, immediately before P2's own mkdir
      attempt executes (i.e. immediately after `ensure_dir_durable`'s own
      `if path.exists(): return` has already evaluated False), it signals
      `p2_passed_exists_check` and then waits for P1's real mkdir to
      complete -- forcing P2's own real mkdir call to race for real
      against an already-completed P1 and receive a genuine
      `FileExistsError`, deterministically.
    - `_fsync_dir` is wrapped only to RECORD (via `p2_fsync_called`,
      IPC-shared) whether P2 itself ever calls it. P1 remains blocked
      before its own fsync for this function's entire duration, so
      whatever is recorded here is unambiguously P2's own action.
    """
    import smartcart.durability_spike._atomic_file as atomic_file_module
    from smartcart.durability_spike._atomic_file import ensure_dir_durable

    real_os_mkdir = os.mkdir

    def synced_mkdir(path_arg: Any, mode: int = 0o777) -> None:
        p2_passed_exists_check.set()
        p1_mkdir_done.wait(timeout=_EVENT_TIMEOUT_SECONDS)
        real_os_mkdir(path_arg, mode)

    os.mkdir = synced_mkdir  # type: ignore[assignment]

    real_fsync_dir = atomic_file_module._fsync_dir

    def recording_fsync_dir(dir_path: Path) -> None:
        p2_fsync_called.value = True
        real_fsync_dir(dir_path)

    atomic_file_module._fsync_dir = recording_fsync_dir

    path = Path(path_str)
    try:
        ensure_dir_durable(path)
        result_queue.put(("returned",))
    except Exception as exc:  # pragma: no cover - safety net so the parent never hangs
        result_queue.put(("raised", repr(exc)))


def test_ensure_dir_durable_fileexists_loser_returns_without_confirming_durability_itself(
    tmp_path: Path,
) -> None:
    """RED by design against the current implementation: proves the
    `except FileExistsError: return` branch returns without the LOSING
    process ever having called `_fsync_dir(parent)` itself."""
    path = tmp_path / "racing_dir"

    p2_passed_exists_check = _CTX.Event()
    p1_mkdir_done = _CTX.Event()
    release_p1_fsync = _CTX.Event()
    p2_fsync_called = _CTX.Value("b", False)
    result_queue = _CTX.Queue()

    p1 = _CTX.Process(
        target=_e_p1_worker,
        args=(str(path), p2_passed_exists_check, p1_mkdir_done, release_p1_fsync),
    )
    p2 = _CTX.Process(
        target=_e_p2_worker,
        args=(str(path), p2_passed_exists_check, p1_mkdir_done, p2_fsync_called, result_queue),
    )
    p1.start()
    p2.start()
    try:
        p2.join(timeout=_JOIN_TIMEOUT_SECONDS)
        outcome = result_queue.get(timeout=_QUEUE_GET_TIMEOUT_SECONDS)

        # P1 is still blocked before its own _fsync_dir at this point --
        # it has not called it. Whatever p2_fsync_called shows is
        # unambiguously P2's own action, not P1's.
        assert outcome[0] == "returned", f"expected a normal return, got {outcome}"
        assert p2_fsync_called.value, (
            "required contract: ensure_dir_durable's FileExistsError branch must "
            "not return successfully without the calling process itself having "
            "confirmed the parent directory via its own _fsync_dir call -- it "
            "currently does not"
        )
    finally:
        release_p1_fsync.set()
        p1.join(timeout=_JOIN_TIMEOUT_SECONDS)


# --- G: regular-file collision at target path --------------------------------


def test_ensure_dir_durable_rejects_a_regular_file_at_target_path(tmp_path: Path) -> None:
    """Required contract: `ensure_dir_durable(path)` may only return
    successfully if `path` is an actual directory owned by the storage
    tree's own semantics -- a pre-existing regular file at `path` must be
    rejected specifically with `NotADirectoryError`, never silently
    accepted. Single-process, no IPC needed: this is not a race, it is
    `ensure_dir_durable`'s own `if path.exists(): return` treating ANY
    existing filesystem entry as sufficient, regardless of its type.

    Exercises the CURRENT implementation as-is, unmodified.
    """
    from smartcart.durability_spike._atomic_file import ensure_dir_durable

    parent = tmp_path / "durable_parent"
    parent.mkdir()
    target = parent / "not_a_directory"
    target.write_bytes(b"this is a regular file, not a directory")

    with pytest.raises(NotADirectoryError):
        ensure_dir_durable(target)

    # Must not have been silently treated as durable: still a regular
    # file, never turned into (or replaced by) a directory.
    assert target.is_file()
    assert not target.is_dir()


# --- F: existing-path fast-path defect --------------------------------------


def _f_p1_worker(path_str: str, mkdir_done: Any, release_p1_fsync: Any) -> None:
    """P1: create `path` for real (a genuine, unpatched mkdir), signal
    completion, then block before calling its own `_fsync_dir` until
    explicitly released."""
    import smartcart.durability_spike._atomic_file as atomic_file_module

    path = Path(path_str)
    path.mkdir()
    mkdir_done.set()
    release_p1_fsync.wait(timeout=_EVENT_TIMEOUT_SECONDS)
    atomic_file_module._fsync_dir(path.parent)


def _f_p2_worker(
    path_str: str, mkdir_done: Any, p2_fsync_called: Any, result_queue: Any
) -> None:
    """P2: waits until P1's mkdir is known to have completed (so
    `path.exists()` is True), then calls the REAL, unmodified
    `ensure_dir_durable(path)` -- exercising the `if path.exists(): return`
    fast path specifically. Records (independently of test E's mechanism)
    whether P2 itself ever calls `_fsync_dir`."""
    import smartcart.durability_spike._atomic_file as atomic_file_module
    from smartcart.durability_spike._atomic_file import ensure_dir_durable

    mkdir_done.wait(timeout=_EVENT_TIMEOUT_SECONDS)

    real_fsync_dir = atomic_file_module._fsync_dir

    def recording_fsync_dir(dir_path: Path) -> None:
        p2_fsync_called.value = True
        real_fsync_dir(dir_path)

    atomic_file_module._fsync_dir = recording_fsync_dir

    path = Path(path_str)
    try:
        ensure_dir_durable(path)
        result_queue.put(("returned",))
    except Exception as exc:  # pragma: no cover - safety net so the parent never hangs
        result_queue.put(("raised", repr(exc)))


def test_ensure_dir_durable_existing_path_fast_return_skips_confirming_durability(
    tmp_path: Path,
) -> None:
    """RED by design against the current implementation: proves the
    `if path.exists(): return` fast path returns without EVER calling
    `_fsync_dir`, even when the directory was just created by a DIFFERENT
    process. Structurally distinct from test E's FileExistsError branch --
    both share the same root cause (trusting another process's directory
    creation without independently confirming it), but they are two
    different lines of code and must be proven independently."""
    path = tmp_path / "racing_dir_2"

    mkdir_done = _CTX.Event()
    release_p1_fsync = _CTX.Event()
    p2_fsync_called = _CTX.Value("b", False)
    result_queue = _CTX.Queue()

    p1 = _CTX.Process(target=_f_p1_worker, args=(str(path), mkdir_done, release_p1_fsync))
    p2 = _CTX.Process(
        target=_f_p2_worker, args=(str(path), mkdir_done, p2_fsync_called, result_queue)
    )
    p1.start()
    p2.start()
    try:
        p2.join(timeout=_JOIN_TIMEOUT_SECONDS)
        outcome = result_queue.get(timeout=_QUEUE_GET_TIMEOUT_SECONDS)

        assert outcome[0] == "returned", f"expected a normal return, got {outcome}"
        assert p2_fsync_called.value, (
            "required contract: ensure_dir_durable must not return successfully "
            "without the calling process itself having confirmed the parent "
            "directory via its own _fsync_dir call, even when path already "
            "exists because another process created it -- it currently does not"
        )
    finally:
        release_p1_fsync.set()
        p1.join(timeout=_JOIN_TIMEOUT_SECONDS)


# --- H: symlink collision at target path --------------------------------


def test_ensure_dir_durable_rejects_symlink_to_directory_at_target_path(tmp_path: Path) -> None:
    """Required contract: a symlink must never be accepted as a
    storage-tree directory, even when it resolves to a valid real
    directory -- `ensure_dir_durable(path)` must reject it specifically
    with `NotADirectoryError`, exactly like a regular file (test G).
    Single-process, no IPC needed: not a race, `ensure_dir_durable`'s own
    `if path.exists(): return` follows symlinks for existence (default
    `pathlib`/`os` symlink-following semantics) and returns successfully
    regardless of what `path` actually IS on disk versus what it merely
    resolves to.

    Exercises the CURRENT implementation as-is, unmodified.
    """
    from smartcart.durability_spike._atomic_file import ensure_dir_durable

    parent = tmp_path / "durable_parent_2"
    parent.mkdir()
    real_dir = tmp_path / "real_directory_elsewhere"
    real_dir.mkdir()
    target = parent / "symlink_not_a_real_directory"
    target.symlink_to(real_dir, target_is_directory=True)

    assert target.exists()
    assert target.is_symlink()
    assert target.is_dir()  # resolves through the symlink to a valid real directory

    with pytest.raises(NotADirectoryError):
        ensure_dir_durable(target)

    # Neither the symlink itself nor what it points to may be disturbed.
    assert target.is_symlink()
    assert os.readlink(target) == str(real_dir)
    assert real_dir.is_dir()
