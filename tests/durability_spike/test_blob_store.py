"""BlobStore: metadata-blind, content-addressed storage primitive."""

from __future__ import annotations

import hashlib
from pathlib import Path

from smartcart.durability_spike.blob_store import BlobStore


def test_put_then_get_round_trips_bytes_exactly(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"\x00\x01hello world" * 100

    content_hash, payload_ref = store.put(data)

    assert content_hash == hashlib.sha256(data).hexdigest()
    assert store.get(payload_ref) == data
    assert store.exists(content_hash)


def test_put_is_idempotent_and_never_creates_a_second_copy(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    data = b"same bytes"

    first_hash, first_ref = store.put(data)
    second_hash, second_ref = store.put(data)

    assert first_hash == second_hash
    assert first_ref == second_ref
    assert len(list(tmp_path.rglob("*.bin"))) == 1


def test_distinct_bytes_get_distinct_blobs(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    hash_a, _ = store.put(b"A")
    hash_b, _ = store.put(b"B")

    assert hash_a != hash_b
    assert len(list(tmp_path.rglob("*.bin"))) == 2


def test_atomic_write_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    store.put(b"content")

    leftover_temp_files = [p for p in tmp_path.rglob(".tmp-*") if p.is_file()]
    assert leftover_temp_files == []


def test_unknown_content_hash_does_not_exist(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    assert not store.exists("0" * 64)
