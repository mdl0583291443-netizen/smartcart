"""Focused Crash-Durability Spike (docs/adr/0010).

Two independent pieces:

- `blob_store`: a metadata-blind, content-addressed blob storage
  primitive.
- `staging`: a thin crash-safe handoff/staging layer built on top of it,
  which owns sequencing and `collected_at`.

Collectors (`smartcart.collectors.*`) must never import this module, and
this module must never import `smartcart.db_spike` or create any
`ArtifactOccurrence` -- see docs/adr/0008 and docs/adr/0010.
"""

from __future__ import annotations
