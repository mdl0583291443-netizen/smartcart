"""ArtifactContent persistence: canonical content identity and dedup.

Identity is SHA-256 over the exact decompressed/extracted source payload
bytes, over the boundary established in the Collector Contract Inspection:
post-transport-normalization/extraction, pre-parser, BOM-inclusive, no
decoding/re-encoding/normalization/reserialization. This module computes
the hash from whatever bytes it is given -- it is the caller's
responsibility to pass exactly that boundary's bytes (see
docs/adr/0009-focused-db-spike.md); this module does not re-derive or
verify the boundary itself.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pg8000.native

from smartcart.db_spike.db import transaction


def compute_content_hash(payload_bytes: bytes) -> str:
    """Canonical ArtifactContent identity: lowercase hex SHA-256 of the
    exact bytes given (see module docstring for the required boundary)."""
    return hashlib.sha256(payload_bytes).hexdigest()


@dataclass(frozen=True)
class ArtifactContentRecord:
    content_id: int
    content_hash: str
    payload_size_bytes: int


def insert_or_get_content(
    conn: pg8000.native.Connection, payload_bytes: bytes
) -> ArtifactContentRecord:
    """Insert one canonical payload, or return the existing identity if
    this exact payload's hash is already durable.

    Never creates a second ArtifactContent row for the same content_hash
    (Round 1 test 2): the content_hash UNIQUE constraint is the source of
    truth for uniqueness, not application-level check-then-insert logic,
    so this remains correct even under concurrent callers inserting the
    same payload.
    """
    content_hash = compute_content_hash(payload_bytes)
    with transaction(conn):
        rows = conn.run(
            """
            INSERT INTO artifact_content (content_hash, payload_bytes, payload_size_bytes)
            VALUES (:content_hash, :payload_bytes, :payload_size_bytes)
            ON CONFLICT (content_hash)
            DO UPDATE SET content_hash = excluded.content_hash
            RETURNING content_id, content_hash, payload_size_bytes
            """,
            content_hash=content_hash,
            payload_bytes=payload_bytes,
            payload_size_bytes=len(payload_bytes),
        )
    content_id, returned_hash, payload_size_bytes = rows[0]
    return ArtifactContentRecord(
        content_id=content_id,
        content_hash=returned_hash,
        payload_size_bytes=payload_size_bytes,
    )


def get_content_by_hash(
    conn: pg8000.native.Connection, content_hash: str
) -> ArtifactContentRecord | None:
    rows = conn.run(
        """
        SELECT content_id, content_hash, payload_size_bytes
        FROM artifact_content WHERE content_hash = :content_hash
        """,
        content_hash=content_hash,
    )
    if not rows:
        return None
    content_id, returned_hash, payload_size_bytes = rows[0]
    return ArtifactContentRecord(
        content_id=content_id,
        content_hash=returned_hash,
        payload_size_bytes=payload_size_bytes,
    )


def count_content_rows(conn: pg8000.native.Connection) -> int:
    """Test/inspection helper: total ArtifactContent row count."""
    rows = conn.run("SELECT count(*) FROM artifact_content")
    count: int = rows[0][0]
    return count
