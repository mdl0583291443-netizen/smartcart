"""Fault injection at the filesystem-durability primitive itself.

Proves the temp-file cleanup path in
`smartcart.durability_spike._atomic_file.atomic_write_bytes`'s
`except BaseException` handler: a failure during the atomic rename must
never leave a partially-written final path visible, and must not leak its
temp file. No filesystem test framework or process-kill is used --
deterministic fault injection (monkeypatching `os.replace`) at the exact
durability boundary is sufficient (and matches the technique already used
for the staging-layer crash-window tests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from smartcart.durability_spike._atomic_file import atomic_write_bytes, ensure_dir_durable


def test_failed_replace_leaves_no_partial_final_file_or_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_replace(src: object, dst: object) -> None:
        raise OSError("simulated crash during atomic rename")

    monkeypatch.setattr("os.replace", failing_replace)

    target = tmp_path / "sub" / "blob.bin"
    with pytest.raises(OSError):
        atomic_write_bytes(target, b"payload")

    assert not target.exists()
    assert list(tmp_path.rglob(".tmp-*")) == []


def test_successful_write_then_failed_rewrite_leaves_original_bytes_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `final_path` already holds durable bytes, a later failed write
    attempt to the same path must not corrupt or truncate what is already
    there (the failure happens on the temp file / rename, never in place)."""
    target = tmp_path / "blob.bin"
    atomic_write_bytes(target, b"original durable bytes")

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("simulated crash during atomic rename")

    monkeypatch.setattr("os.replace", failing_replace)

    with pytest.raises(OSError):
        atomic_write_bytes(target, b"new bytes that must never land")

    assert target.read_bytes() == b"original durable bytes"
    assert list(tmp_path.rglob(".tmp-*")) == []


def test_ensure_dir_durable_reconfirms_the_full_ancestor_chain_on_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current contract: `ensure_dir_durable(target)` reconfirms EVERY
    non-root directory level in the full ancestor chain up to the real
    filesystem root -- including ancestors that already existed long
    before this call (e.g. `/`, `/tmp`, and every real system directory
    in between), not merely the levels this specific call happens to
    create. (Retires the older, narrower claim that only newly-created
    ancestors get fsynced -- that optimization was the root cause of the
    cross-process durability gap tests E/F now guard against.)

    The expected fsync sequence is derived dynamically from `target`'s
    actual ancestor chain, never hardcoded to any particular filesystem
    depth -- this must hold regardless of how deep `tmp_path` happens to
    be on whatever machine runs the test. Filesystem root itself is the
    recursion base case (`path.parent == path`): it is never `mkdir`'d or
    treated as a newly-created child, though it does appear once in the
    expected sequence, as the `_fsync_dir` argument confirming its own
    immediate child -- exactly like any other ancestor's parent would.
    """
    import smartcart.durability_spike._atomic_file as atomic_file_module

    fsynced: list[Path] = []
    real_fsync_dir = atomic_file_module._fsync_dir

    def recording_fsync_dir(dir_path: Path) -> None:
        fsynced.append(dir_path)
        real_fsync_dir(dir_path)

    monkeypatch.setattr(atomic_file_module, "_fsync_dir", recording_fsync_dir)

    target = tmp_path / "a" / "b" / "c"

    # Derived dynamically: walk target's real ancestor chain up to (and
    # including, as a parent value) filesystem root, then reverse -- the
    # recursive implementation confirms the shallowest ancestor first and
    # unwinds down to target's own immediate parent last.
    expected_order: list[Path] = []
    current = target
    while current.parent != current:
        expected_order.append(current.parent)
        current = current.parent
    expected_order.reverse()

    ensure_dir_durable(target)

    assert target.is_dir()
    assert fsynced == expected_order


def test_ensure_dir_durable_repeated_call_on_existing_path_still_reconfirms_full_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Current contract: a second call to `ensure_dir_durable(path)` for a
    path that already fully exists must still succeed AND must still
    reconfirm every non-root ancestor in the full chain via its own fresh
    `_fsync_dir` calls -- it must NOT perform zero fsyncs. This proves
    idempotent *correctness* (repeated calls never fail and never skip
    confirming durability), not idempotent *cheapness*. (Retires the
    older "true no-op on repeat calls" claim -- trusting a prior,
    unconfirmed call without reconfirming it is exactly the class of bug
    this module now closes; see tests E/F.)

    Expectations are derived dynamically from `nested`'s actual ancestor
    chain, never hardcoded to a specific filesystem depth.
    """
    nested = tmp_path / "a" / "b" / "c"
    ensure_dir_durable(nested)  # first call: creates everything

    import smartcart.durability_spike._atomic_file as atomic_file_module

    fsynced: list[Path] = []
    real_fsync_dir = atomic_file_module._fsync_dir

    def recording_fsync_dir(dir_path: Path) -> None:
        fsynced.append(dir_path)
        real_fsync_dir(dir_path)

    monkeypatch.setattr(atomic_file_module, "_fsync_dir", recording_fsync_dir)

    expected_order: list[Path] = []
    current = nested
    while current.parent != current:
        expected_order.append(current.parent)
        current = current.parent
    expected_order.reverse()

    ensure_dir_durable(nested)  # second call: everything already exists

    assert nested.is_dir()
    assert fsynced != []
    assert fsynced == expected_order
