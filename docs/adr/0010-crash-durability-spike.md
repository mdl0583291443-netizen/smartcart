# 0010. Crash-durability spike: raw transport staging as temporary crash-safety infrastructure

## Status

Accepted

## Context

Collectors currently produce parsed, validated output entirely in memory
(docs/adr/0004); nothing about acquiring a source file survives a process
crash between "the retailer finished sending bytes" and "those bytes were
turned into something durable." Before any future persistence work can
rely on a `collected_at` value, that value's semantic and its survival
across a crash need to be pinned down, independent of -- and prior to --
the still-undecided production database/ingestion design.

This ADR authorizes a narrowly-scoped "Focused Crash-Durability Spike"
proving that:

- `collected_at` can be captured once, at the moment the full raw source
  transport bytes have been received (before decompression/extraction),
  as a timezone-aware UTC value;
- that value and the raw bytes it belongs to can be made crash-safe
  together, as one recoverable unit, using real filesystem durability
  semantics (fsync + atomic rename), not just `open().write()`;
- canonical extraction/decompression can be safely rerun from the staged
  raw bytes after a crash without ever regenerating or altering
  `collected_at`;
- canonical payload identity (the SHA-256 boundary already fixed by
  `smartcart.db_spike.content`) and its own blob-first/metadata-second
  durability sequencing survive a crash between the two steps without
  silently promoting an orphaned blob into usable evidence.

Two existing ADRs bear directly on this:

- ADR 0008 ("Collector-to-persistence boundary") forbids creating
  `storage/`/`persistence/`-shaped scaffolding until DB/data-model design
  is complete, and forbids collectors from depending on any such module.
- ADR 0009 ("Focused DB spike") already recorded one narrow, explicit
  exception to that timing rule for `db_spike/`, and established the
  pattern this ADR follows: name the module so it reads as a bounded,
  provisional experiment, not a committed design, and state exactly what
  the exception does and does not cover.

This spike is deliberately independent of `db_spike`/PostgreSQL: it proves
a filesystem-level crash-safety mechanism, not a relational schema, and
introduces no new runtime dependency.

**This is a correction of an earlier, different `collected_at` capture
point, not a silent semantic change.** `tests/db_spike/test_real_output_acceptance.py`
(Round 1.5's real-collector acceptance run) captures its
`_acceptance_collected_at()` value *after* `transport.decompress()`/
`transport.normalize()` and after parsing -- i.e., at canonical-payload
availability time -- and says so explicitly in its own docstring ("this
acceptance run therefore uses an EXPLICITLY-CONTROLLED, CLEARLY-LABELED
test fixture timestamp... captured at this integration boundary
immediately after each download call returns... not a demonstration that
a production collected_at handoff exists"). That test already flagged its
own timestamp as a temporary stand-in, not a settled semantic. This ADR is
what settles it: `collected_at` means the moment full raw source
transport bytes are received, *before* decompression/extraction --
strictly earlier than where that acceptance test's fixture value is
captured. Nothing in this spike changes `test_real_output_acceptance.py`
itself; the two are not reconciled by this ADR, and doing so (wiring a
real acquisition-time `collected_at` into that acceptance path) remains
separate future work (see Consequences).

## Decision

**Scope of the exception.** ADR 0008's scaffolding-timing clause is
narrowly superseded, only for this bounded spike. ADR 0008's substantive
boundary is fully intact and unaffected by this ADR: collectors remain
DB-unaware and own no persistence schema, transactions, or storage
sequencing of any kind -- they must never import
`smartcart.durability_spike` (nor any future production equivalent), and
this module may depend on collector output (raw bytes, and existing
transport/parse functions used as opaque callables) when justified, never
the reverse.

**Module naming.** The spike lives in `src/smartcart/durability_spike/`
(and `tests/durability_spike/`), following ADR 0009's naming convention:
the name signals a provisional experiment, not the eventual production
staging/storage module name. Promoting it is a separate future decision.

**Two responsibilities, kept separate:**

- `blob_store.BlobStore` -- a metadata-blind, content-addressed blob
  primitive (`put(bytes) -> (content_hash, payload_ref)`,
  `get(payload_ref) -> bytes`) on the local filesystem. It knows nothing
  about retailers, `collected_at`, or staging sequencing.
- `staging.CrashSafeStagingStore` -- owns sequencing and carries
  `collected_at`. It stages raw bytes (`stage_raw`), recovers them
  (`recover_raw`), and finalizes canonical payloads from staged raw bytes
  via a caller-supplied deterministic `extract` callable
  (`finalize_canonical`, `recover_canonical`). `collected_at` is only ever
  read back from the durable raw record; no code path in this module can
  regenerate or alter it during canonical finalization.

**Raw staging commit point and orphan invariant.** A raw staged
observation is promotable/recoverable through the public API
(`recover_raw`) only once BOTH of the following are durable: the raw blob
itself, and a metadata record referencing it that carries the original
`collected_at`. A raw blob that is durable on the filesystem but has no
corresponding metadata record is an incomplete orphan -- it is never
returned by `recover_raw`, regardless of which `CrashSafeStagingStore`
instance asks (a fresh instance pointed at the same durable location gets
the same answer as the instance that wrote it). It may remain detectable
(`raw_blob_exists`) and reclaimable, but this spike does not reconcile or
clean it up. The identical rule applies to canonical finalization:
`recover_canonical` never returns a canonical blob that is durable without
its own metadata record (`canonical_blob_exists` detects that orphan
case). `collected_at` itself is only ever read back from a durable raw
metadata record; `stage_raw` additionally enforces that the value supplied
is an aware UTC datetime (`utcoffset() == timedelta(0)`) -- a naive
datetime or an arbitrary aware offset (e.g. `+03:00`) is rejected outright
before anything is written, never silently converted.

**Durability mechanism.** Real POSIX crash-safe sequencing: write to a
temp file in the target directory, `fsync` the file, `os.replace()` it
into place (atomic same-filesystem rename), then `fsync` the containing
directory (the rename itself is not guaranteed durable across a crash
until the directory entry is fsynced). No configuration, no pluggable
backend, no cloud abstraction -- a local filesystem path is the only
supported target, and callers treat `payload_ref` as opaque.

**Ancestor-directory and write-once metadata durability (proven by
deterministic cross-process test, see `tests/durability_spike/`).** Two
properties beyond the single-file mechanism above are now proven, not
merely assumed: metadata publication (`stage_raw`/`finalize_canonical`)
is write-once across concurrent OS processes via `os.link`'s atomic
create-if-absent semantics, never `os.replace` -- a losing process
detects a conflicting concurrent publication and raises rather than
silently overwriting the winner, while identical concurrent publication
remains idempotent. And `ensure_dir_durable` confirms every ancestor
directory's parent-entry durability via its own `fsync` call on every
invocation -- whether it created the directory, found it already valid,
or lost a concurrent creation race to another process's real directory --
rather than trusting that a different process's directory creation is
durable without independently confirming it. A regular file or symlink
occupying a path this module expects to be a directory is rejected
(`NotADirectoryError`), never silently treated as durable, even when a
symlink resolves to a valid directory. Concurrent deletion or replacement
of an ancestor directory mid-call remains outside this module's threat
model -- only creation/collision races are handled. As throughout this
module, these guarantees hold only for a native Linux/WSL ext4-backed
filesystem, never a Windows-mounted path accessed via `/mnt/c` (DrvFs) or
a network filesystem (NFS, SMB/CIFS, etc.); and the fault-injection tests
proving them demonstrate control-flow durability semantics -- what the
code does and does not report as successful -- not literal
post-power-loss persistence, which would require real crash/reboot
testing outside the scope of a monkeypatched, single-host test suite.

**Race-loser fsync dependency is a filesystem assumption, not a Python
guarantee.** The ancestor-directory confirmation described above depends
on a specific native Linux/ext4 directory-fsync property: when one
process's `mkdir` wins a race and creates a directory entry, and a second
process's `mkdir` loses that race (observing `FileExistsError`), the
losing process's own, successful `fsync(parent)` call is relied upon to
durably confirm the *winner's* directory entry -- the one now present in
that parent directory -- not merely the losing process's own prior
actions. This works because `fsync` on a directory descriptor flushes
that directory's current metadata state as the filesystem itself sees
it, regardless of which process's operation produced that state; it is a
property of the underlying filesystem's `fsync(2)`/directory-entry
durability model, not of Python, not of `os.mkdir`, and not of anything
this module's own code does to make it true. This dependency holds only
under the native Linux/WSL ext4-backed filesystem this spike already
scopes itself to, and is explicitly NOT generalized to a Windows-mounted
path accessed via `/mnt/c` (DrvFs), a network filesystem (NFS,
SMB/CIFS, etc.), or any other filesystem without its own separate
validation of this exact property.

**Accepted residual window: a directory entry created but never
fsync-confirmed by anyone.** A directory entry can be successfully
created by the winning `mkdir` and yet remain durability-unconfirmed if
the winning creator AND every racing/confirming caller crash before any
of them successfully completes its `fsync(parent)` call -- this protocol
has not, at that point, durably confirmed that entry. This is an
accepted, recoverable residual window, not a claim that no such window
exists: a later successful call re-walks and reconfirms the full
ancestor chain from scratch and, if the entry is still present, closes
the confirmation gap on that attempt via its own fresh `fsync`. The
design therefore treats this window as recoverable-by-retry, never as
proof that the original, pre-crash directory entry itself survived a
literal power loss -- confirming actual survival across a real
crash/reboot is outside what a monkeypatched, single-host fault-injection
test suite can prove, and this ADR makes no stronger claim than that.

**What this spike explicitly does not do**, per its authorizing task
scope: no `ArtifactOccurrence`, no Round 2 activation, no PostgreSQL
dependency, no scheduler/queue/worker/retry framework, no orphan
cleanup/reconciliation engine, no retention policy, no cloud/object-store
integration, and no `source`/`chain`/`store` metadata in the staging
record. Raw transport bytes staged here are temporary crash-safety
infrastructure only -- per the Data Strategy, they do not become
permanent historical evidence merely because they are durably staged;
canonical payload identity (`content_hash`) remains the primary retained
evidence, exactly as `smartcart.db_spike.content` already establishes.

## Consequences

- `src/smartcart/durability_spike/` and `tests/durability_spike/` now
  exist as a second, independent "spike"-named module alongside
  `db_spike/`, requiring no PostgreSQL and no new runtime dependency.
- Collectors remain unmodified and unaware of this module, verified by
  inspection (as with `db_spike`, not yet by an automated architectural
  test).
- `collected_at`'s semantic (full raw transport bytes received, captured
  once, before decompression) is now proven to survive a crash at each of
  the boundaries this spike tested; a future production ingestion design
  may adopt this mechanism, but adopting it, deciding raw-bytes retention
  duration/cleanup, and wiring `ArtifactOccurrence.collected_at` to a real
  acquisition timestamp all remain separate, undecided future work.
- This ADR does not decide: production raw-artifact retention/cleanup
  policy, how a future ingestion orchestrator discovers pending staged
  raw records to finalize, or whether `durability_spike`'s mechanism (as
  opposed to its filesystem-only implementation) becomes the production
  approach.
- Ancestor-directory durability confirmation (`ensure_dir_durable`) and
  cross-process write-once metadata publication (`os.link`-based, never
  `os.replace`) are now proven by deterministic multi-process regression
  tests, not merely single-process fault injection; both hold only for a
  native Linux/WSL ext4-backed filesystem, explicitly excluding
  `/mnt/c`/DrvFs and network filesystems, and neither claims to prove
  literal post-power-loss persistence.
