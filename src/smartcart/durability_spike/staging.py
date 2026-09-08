"""Thin crash-safe handoff/staging layer over BlobStore.

Owns exactly two things: sequencing (raw stage -> canonical finalize) and
carrying `collected_at` across that sequence unchanged. See
docs/adr/0010-crash-durability-spike.md for the invariants this
implements and the closed-scope boundary it stays inside of (no
`ArtifactOccurrence`, no scheduler, no retention policy, no database).

`collected_at` is supplied once, by the caller, to `stage_raw` -- the
moment full raw source transport bytes have been received. Every later
step (`recover_raw`, `finalize_canonical`, `recover_canonical`) only ever
reads that same value back from the durable raw record; nothing in this
module can regenerate, override, or otherwise touch it. Both `stage_raw`
and `finalize_canonical` are write-once *across concurrent OS processes*,
not just within one process: metadata publication goes through
`_atomic_file.atomic_write_once_bytes`, whose `os.link`-based
create-if-absent semantics are enforced by the kernel, not by an
in-application check-then-write that a second process could race past.
Re-invoking either for a raw_content_hash that already has a durable
metadata record either returns the existing record unchanged (if the
freshly computed record is byte-identical) or raises
`ConflictingMetadataError` (if it differs) -- never a silent overwrite,
and never a last-writer-wins race between two processes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from smartcart.durability_spike._atomic_file import (
    ConflictingWriteOnceError,
    atomic_write_once_bytes,
    ensure_dir_durable,
)
from smartcart.durability_spike.blob_store import BlobStore


class NotStagedError(Exception):
    """Raised when canonical finalization/recovery is attempted for a
    raw_content_hash with no durable staged raw record."""


class ConflictingMetadataError(Exception):
    """Raised when a re-stage or re-finalize attempt's freshly computed
    record conflicts with an already-durable metadata record for the same
    content hash -- e.g. the same raw bytes staged again with a different
    collected_at, or a non-deterministic `extract` producing a different
    canonical hash on a `finalize_canonical` retry -- including when the
    conflicting record was published by a concurrent OS process, not just
    a prior call in this process. An identical re-computation is a no-op
    returning the existing record; a conflicting one fails closed here
    rather than silently overwriting durable state."""


def _require_utc(value: datetime) -> None:
    """Fail closed: collected_at must be an aware UTC datetime, not merely
    tz-aware. An arbitrary aware offset (e.g. +03:00) is rejected outright
    rather than silently converted -- this boundary has no license to
    reinterpret a caller's timestamp, only to accept or refuse it."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("collected_at must be an aware UTC datetime; got a naive datetime.")
    if value.utcoffset() != timedelta(0):
        raise ValueError(
            "collected_at must be UTC (utcoffset() == timedelta(0)); got "
            f"utcoffset()={value.utcoffset()!r}. This boundary fails closed instead of "
            "silently converting an arbitrary aware offset."
        )


@dataclass(frozen=True)
class RawStagedEvidence:
    """Complete raw source bytes, already durably staged, plus the
    collected_at they were staged with."""

    raw_content_hash: str
    raw_payload_ref: str
    collected_at: datetime


@dataclass(frozen=True)
class DurableCanonicalEvidence:
    """Minimum durable canonical recovery metadata: canonical content
    identity, where to read its bytes, and the original raw-acquisition
    collected_at (never regenerated during canonical finalization)."""

    content_hash: str
    payload_ref: str
    collected_at: datetime


def _read_json(path: Path) -> dict[str, str]:
    record: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return record


class CrashSafeStagingStore:
    """Sequencing + collected_at handoff for one raw-acquisition ->
    canonical-finalization lifecycle. A fresh instance pointed at the same
    `root` recovers purely from durable filesystem state -- it holds no
    other state itself.
    """

    def __init__(self, root: Path) -> None:
        self._raw_blobs = BlobStore(root / "raw_blobs")
        self._canonical_blobs = BlobStore(root / "canonical_blobs")
        self._raw_meta_dir = root / "raw_meta"
        self._canonical_meta_dir = root / "canonical_meta"
        ensure_dir_durable(self._raw_meta_dir)
        ensure_dir_durable(self._canonical_meta_dir)

    def _raw_meta_path(self, raw_content_hash: str) -> Path:
        return self._raw_meta_dir / f"{raw_content_hash}.json"

    def _canonical_meta_path(self, raw_content_hash: str) -> Path:
        return self._canonical_meta_dir / f"{raw_content_hash}.json"

    def stage_raw(self, raw_bytes: bytes, collected_at: datetime) -> RawStagedEvidence:
        """Durably preserve raw transport bytes + collected_at as one
        recoverable staged unit.

        Sequencing is blob-first, metadata-second: the raw bytes are made
        durable before the metadata record that promotes them into a
        recoverable staged unit. A crash before the metadata record is
        durable leaves, at worst, an unreferenced (but detectable --
        see `raw_blob_exists`) raw blob and no recoverable staged record:
        an incomplete orphan, never a promotable staged record and never
        a fabricated collected_at.

        Raises ValueError if `collected_at` is not an aware UTC datetime
        (see `_require_utc`); this is checked before anything is written.

        Write-once across concurrent OS processes: metadata publication
        goes through `atomic_write_once_bytes`, whose `os.link`-based
        create-if-absent semantics are enforced by the kernel. An
        identical re-computation (same raw_payload_ref, same
        collected_at) -- whether a retry in this process or a genuinely
        concurrent call in another process -- is a no-op that returns the
        equivalent record; a conflicting one (most notably a different
        collected_at for byte-identical raw content) raises
        `ConflictingMetadataError` instead of silently replacing the
        original acquisition timestamp. There is no check-then-write
        window a second process can race past: `recover_raw` is not used
        here as a synchronization mechanism.
        """
        _require_utc(collected_at)

        raw_content_hash, raw_payload_ref = self._raw_blobs.put(raw_bytes)
        candidate = RawStagedEvidence(
            raw_content_hash=raw_content_hash,
            raw_payload_ref=raw_payload_ref,
            collected_at=collected_at,
        )
        record_bytes = json.dumps(
            {
                "raw_content_hash": raw_content_hash,
                "raw_payload_ref": raw_payload_ref,
                "collected_at": collected_at.isoformat(),
            }
        ).encode("utf-8")

        try:
            atomic_write_once_bytes(self._raw_meta_path(raw_content_hash), record_bytes)
        except ConflictingWriteOnceError as exc:
            existing = self.recover_raw(raw_content_hash)
            existing_collected_at = (
                existing.collected_at.isoformat() if existing is not None else "<unavailable>"
            )
            raise ConflictingMetadataError(
                f"Durable raw metadata for raw_content_hash={raw_content_hash!r} already "
                f"exists with collected_at={existing_collected_at!r}; refusing to overwrite "
                f"it with a conflicting collected_at={collected_at.isoformat()!r}."
            ) from exc

        return candidate

    def recover_raw(self, raw_content_hash: str) -> RawStagedEvidence | None:
        """Recover a previously staged raw record from durable state
        only. Returns None if no durable staged record exists (either
        never staged, or staging was interrupted before completion)."""
        path = self._raw_meta_path(raw_content_hash)
        if not path.exists():
            return None
        record = _read_json(path)
        return RawStagedEvidence(
            raw_content_hash=record["raw_content_hash"],
            raw_payload_ref=record["raw_payload_ref"],
            collected_at=datetime.fromisoformat(record["collected_at"]),
        )

    def get_raw_bytes(self, staged: RawStagedEvidence) -> bytes:
        return self._raw_blobs.get(staged.raw_payload_ref)

    def raw_blob_exists(self, raw_content_hash: str) -> bool:
        """Detect a raw blob that is durable on its own, regardless of
        whether a raw metadata record references it -- for
        test/inspection only, mirroring `canonical_blob_exists`. A raw
        blob without a metadata record is an incomplete orphan: it is
        never returned by `recover_raw` and this store never reconciles
        or cleans it up itself."""
        return self._raw_blobs.exists(raw_content_hash)

    def finalize_canonical(
        self, raw_content_hash: str, extract: Callable[[bytes], bytes]
    ) -> DurableCanonicalEvidence:
        """Recover staged raw bytes, deterministically extract canonical
        bytes via `extract`, and durably store canonical bytes + minimum
        recovery metadata (content_hash, payload_ref, original
        collected_at).

        Blob-first, metadata-second, same as `stage_raw`: a crash after
        the canonical blob is durable but before the metadata record is
        durable leaves an orphaned-but-detectable canonical blob, never a
        promotable-but-incomplete evidence record.

        `extract` may be rerun any number of times (it must be
        deterministic) without ever changing `collected_at`, which is
        read only from the recovered raw record, never regenerated here.

        Write-once across concurrent OS processes, via the same
        `atomic_write_once_bytes` mechanism `stage_raw` uses. An
        identical re-computation (same content_hash, payload_ref, and
        collected_at) -- whether a retry in this process or a genuinely
        concurrent call in another process -- is a no-op that returns the
        equivalent record; a conflicting one (most notably a different
        content_hash, which would only happen if `extract` violated its
        determinism contract) raises `ConflictingMetadataError` instead of
        silently repointing already durable canonical evidence.
        `recover_raw` here is only used to fetch the (already
        write-once-protected) raw input needed to compute the canonical
        bytes, never as a synchronization mechanism for this method's own
        write.
        """
        staged = self.recover_raw(raw_content_hash)
        if staged is None:
            raise NotStagedError(
                f"No durable staged raw record for raw_content_hash={raw_content_hash!r}; "
                "cannot finalize canonical evidence."
            )
        raw_bytes = self.get_raw_bytes(staged)
        canonical_bytes = extract(raw_bytes)

        content_hash, payload_ref = self._canonical_blobs.put(canonical_bytes)
        candidate = DurableCanonicalEvidence(
            content_hash=content_hash,
            payload_ref=payload_ref,
            collected_at=staged.collected_at,
        )
        record_bytes = json.dumps(
            {
                "content_hash": content_hash,
                "payload_ref": payload_ref,
                "collected_at": staged.collected_at.isoformat(),
            }
        ).encode("utf-8")

        try:
            atomic_write_once_bytes(self._canonical_meta_path(raw_content_hash), record_bytes)
        except ConflictingWriteOnceError as exc:
            existing = self.recover_canonical(raw_content_hash)
            existing_hash = existing.content_hash if existing is not None else "<unavailable>"
            raise ConflictingMetadataError(
                f"Durable canonical metadata for raw_content_hash={raw_content_hash!r} already "
                f"exists with content_hash={existing_hash!r}; refusing to overwrite it with a "
                f"conflicting recomputed content_hash={content_hash!r}."
            ) from exc

        return candidate

    def recover_canonical(self, raw_content_hash: str) -> DurableCanonicalEvidence | None:
        """Recover durable canonical evidence from durable state only.
        Returns None if canonical finalization never completed durably
        for this raw_content_hash (including a blob-only orphan left by a
        crash between blob and metadata durability -- see
        `canonical_blob_exists`)."""
        path = self._canonical_meta_path(raw_content_hash)
        if not path.exists():
            return None
        record = _read_json(path)
        return DurableCanonicalEvidence(
            content_hash=record["content_hash"],
            payload_ref=record["payload_ref"],
            collected_at=datetime.fromisoformat(record["collected_at"]),
        )

    def get_canonical_bytes(self, evidence: DurableCanonicalEvidence) -> bytes:
        return self._canonical_blobs.get(evidence.payload_ref)

    def canonical_blob_exists(self, content_hash: str) -> bool:
        """Detect a canonical blob that is durable on its own, regardless
        of whether a metadata record references it -- for
        test/inspection only. This store never reconciles or cleans up
        such an orphan itself."""
        return self._canonical_blobs.exists(content_hash)
