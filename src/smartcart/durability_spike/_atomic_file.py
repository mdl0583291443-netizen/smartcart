"""Internal filesystem-durability helper shared by blob_store and staging.

Not part of either of this spike's two public responsibilities (see
package docstring) -- just the crash-safe write primitive both are built
on. Linux/WSL only: relies on `os.fsync` working on a directory file
descriptor, and on `os.link`'s atomic create-if-absent guarantee, both of
which are POSIX-specific and require a native, local filesystem (WSL2's
own ext4-backed virtual disk). These guarantees do not extend to a
Windows-mounted path accessed via `/mnt/c` (DrvFs), a network filesystem
(NFS, SMB/CIFS, etc.), or any other filesystem without its own separate
validation -- none of those are supported targets for this module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _fsync_dir(dir_path: Path) -> None:
    """Fsync a directory's entry table, not just a file's contents.

    On Linux, `os.replace()`'s rename is only guaranteed to survive a
    crash once the directory it landed in has itself been fsynced --
    fsyncing the file alone is not sufficient for the *rename* to be
    durable (see the Linux `fsync(2)`/`rename(2)` durability discussion
    for ext4/xfs: a directory entry change needs its own fsync).
    """
    dir_fd = os.open(dir_path, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def ensure_dir_durable(path: Path) -> None:
    """Ensure `path` exists as a real (non-symlink) directory, with the
    caller having independently confirmed -- via its own `_fsync_dir`
    call -- that its parent directory entry is durable, regardless of
    whether this call created `path`, found it already valid, or lost a
    concurrent `mkdir` race to another process's real directory.

    Filesystem root (`path.parent == path`) is the recursion base case.
    Every other, non-root call unconditionally recurses into
    `ensure_dir_durable(path.parent)` first -- reconfirming the full
    ancestor chain on every call, not just the first time a given
    ancestor is created -- then attempts `path.mkdir()`. A `FileExistsError`
    from that attempt means something already occupies `path`: if it is a
    symlink or anything other than a real directory, this raises
    `NotADirectoryError` rather than silently trusting it; if it is a
    genuine pre-existing directory (whether it predates this call or was
    just created by a concurrent process that won the `mkdir` race), this
    falls through exactly like the newly-created case. Either way --
    created it, or found/lost to a valid existing one -- this call always
    reaches its own `_fsync_dir(path.parent)` before returning
    successfully; it never trusts another process's durability
    confirmation in its place.

    Out of scope: concurrent deletion or replacement of an ancestor
    directory while a call is already in flight (e.g. another process
    removing or repointing a directory this call has already recursed
    past) is not handled -- the invariants proven here cover
    creation/collision races only. Fault-injection tests exercising this
    function prove control-flow durability semantics (what the code does
    and does not report as successful), never literal post-power-loss
    persistence, which requires real crash/reboot testing outside the
    scope of a monkeypatched, single-host test suite. As with the rest of
    this module (see its docstring), this guarantee holds only for a
    native Linux/WSL ext4-backed filesystem -- not `/mnt/c`/DrvFs, not a
    network filesystem.
    """
    if path.parent == path:
        return

    ensure_dir_durable(path.parent)

    try:
        path.mkdir()
    except FileExistsError as err:
        if path.is_symlink() or not path.is_dir():
            raise NotADirectoryError(
                f"expected a real directory, got non-directory or symlink: {path}"
            ) from err

    _fsync_dir(path.parent)


def atomic_write_bytes(final_path: Path, data: bytes) -> None:
    """Durably write `data` to `final_path`.

    A process crash at any point during this call leaves `final_path`
    either fully absent (if it didn't already exist) or fully present
    with exactly these bytes -- never truncated or partially written.

    Sequence: durably create any missing ancestor directories
    (`ensure_dir_durable`), write to a temp file in the same directory,
    `fsync` the temp file's contents, atomically rename it into place
    (`os.replace`, which is atomic for a same-filesystem rename on
    POSIX), then `fsync` the directory so the rename itself survives a
    crash.
    """
    ensure_dir_durable(final_path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=final_path.parent, prefix=".tmp-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, final_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    _fsync_dir(final_path.parent)


class ConflictingWriteOnceError(Exception):
    """Raised by `atomic_write_once_bytes` when `final_path` already
    durably exists with content that differs from what this caller tried
    to publish."""


def atomic_write_once_bytes(final_path: Path, data: bytes) -> bool:
    """Durably publish `data` at `final_path` exactly once, safely across
    concurrent OS processes -- not just within one process.

    `atomic_write_bytes` uses `os.replace`, which always wins: a second
    caller silently overwrites whatever the first one wrote, and two
    processes racing a check-then-write around it can both observe "no
    file yet" and both proceed to write, with the second `os.replace`
    winning last-writer-wins. This function instead *publishes*, using
    `os.link`: `link(2)` is a single atomic kernel operation that adds a
    directory entry only if none exists yet, failing with `FileExistsError`
    otherwise -- it can never overwrite. Two processes racing to publish
    the same `final_path` are serialized by the kernel itself; there is no
    in-application window in which both can believe they are first.

    No partial content is ever visible at `final_path`: the full bytes are
    written and fsynced to a temp file in the same directory first, and
    `final_path` is only ever exposed via the single atomic `os.link` call
    once that data is already complete and durable -- unlike
    `open(..., O_CREAT | O_EXCL)`, which would expose `final_path` at its
    final name before the content behind it is written.

    Returns True if this call durably published `final_path` (it did not
    already exist). Returns False if `final_path` already existed with
    byte-identical content -- an idempotent no-op, no write performed.
    Raises `ConflictingWriteOnceError` if `final_path` already existed
    with *different* content; this function never silently overwrites or
    reconciles a conflict.

    On `FileExistsError` from `os.link`, this process fsyncs
    `final_path.parent` itself before trusting/reading `final_path` --
    `fsync` on a directory durabilizes whatever entries currently exist in
    it regardless of which process created them, so a "losing" caller can
    safely complete a winner's durability confirmation even if the winner
    crashed immediately after its own `os.link` succeeded and never called
    fsync at all.
    """
    ensure_dir_durable(final_path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=final_path.parent, prefix=".tmp-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        try:
            os.link(tmp_path, final_path)
        except FileExistsError:
            _fsync_dir(final_path.parent)
            if final_path.read_bytes() == data:
                return False
            raise ConflictingWriteOnceError(
                f"{final_path} already durably exists with content that differs from "
                "what this caller tried to publish; refusing to overwrite it."
            ) from None

        _fsync_dir(final_path.parent)
        return True
    finally:
        tmp_path.unlink(missing_ok=True)
