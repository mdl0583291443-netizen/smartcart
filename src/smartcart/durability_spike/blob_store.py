"""Metadata-blind, content-addressed blob storage primitive.

Knows nothing about retailers, `collected_at`, parsers, or staging
sequencing -- see staging.py for the crash-safe handoff layer built on top
of this. Blob identity is the SHA-256 hex digest of the exact bytes
given; storing the same bytes twice is idempotent and never creates a
second on-disk copy.

Deliberately minimal: no generalized storage-backend abstraction, no
pluggable configuration, no cloud target. `payload_ref` is an opaque
string handle a caller must only pass back to `get`/`exists`, never parse
or construct itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from smartcart.durability_spike._atomic_file import atomic_write_bytes, ensure_dir_durable


class BlobStore:
    """Content-addressed blob storage on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self._root = root
        ensure_dir_durable(self._root)

    def _path_for(self, content_hash: str) -> Path:
        return self._root / content_hash[:2] / content_hash[2:4] / f"{content_hash}.bin"

    def put(self, data: bytes) -> tuple[str, str]:
        """Durably store `data`, returning `(content_hash, payload_ref)`.

        Idempotent: storing byte-identical data twice returns the same
        pair and never creates a second on-disk copy.
        """
        content_hash = hashlib.sha256(data).hexdigest()
        path = self._path_for(content_hash)
        if not path.exists():
            atomic_write_bytes(path, data)
        return content_hash, str(path)

    def get(self, payload_ref: str) -> bytes:
        """Read back the bytes for a previously returned `payload_ref`."""
        return Path(payload_ref).read_bytes()

    def exists(self, content_hash: str) -> bool:
        """Whether a blob with this content_hash is already durable.

        Used only to detect an orphaned blob from the outside (see
        staging.py); this store never reconciles or cleans up orphans
        itself.
        """
        return self._path_for(content_hash).exists()
