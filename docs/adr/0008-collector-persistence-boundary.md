# 0008. Collector-to-persistence boundary

## Status

Accepted

## Context

Phase 1A has now shipped two independent collectors (Shufersal, Rami Levy),
each producing source-faithful raw records plus structured validation/
operational outcomes, entirely in memory (see docs/adr/0004). No database
or persistence layer exists yet, and its physical design (schema, ORM/SQL
choice, price-history strategy, product/store identity model) is
explicitly deferred. Before that layer is designed, the boundary between
"collecting" and "persisting" needs to be fixed, so that later DB work
extends the collectors rather than reaching into them.

## Decision

Collectors are responsible only for:

- source access (discovery/download/transport)
- parsing into source-faithful raw records
- source-level validation
- collector-specific failure isolation (per-file outcomes, run-level vs.
  file-level failure, as already implemented)

Collectors MUST NOT:

- import any future DB/persistence module
- write directly to PostgreSQL (or any other database)
- perform DB transactions
- normalize raw source data merely for storage convenience
- mix database failure semantics (transaction/rollback/retry) with
  collector failure semantics (discovery/download/transport/parse/
  validation outcomes)

Persistence/DB ingestion will consume already-parsed and already-validated
collector output across a one-way dependency boundary: persistence may
depend on collector output types/contracts when justified, but collectors
must never depend on persistence.

The physical structure of the future DB layer is intentionally not
decided yet. No `db/`, `persistence/`, `storage/`, `schema.py`,
`connection.py`, `ingest.py`, `tests/db/`, or equivalent scaffolding
should be created until DB/data-model design is complete.

## Consequences

- Raw fidelity is preserved: collectors never reshape data to suit a
  storage technology that doesn't exist yet.
- Source ingestion stays independent of storage technology -- swapping or
  deferring the DB choice cannot require collector changes.
- Collector failure behavior (per-file, per-run outcomes) stays separate
  from database transaction/recovery behavior; the two are not designed
  together and must not be conflated later.
- Module decomposition for persistence is deferred until the DB/data-model
  decisions it depends on are actually settled, avoiding scaffolding built
  around still-unresolved choices.
- This ADR does not define: database schema, ORM/SQL technology,
  price-history model, product/store identity model, transaction strategy,
  idempotency strategy, migrations structure, or normalization/matching
  design. Each remains open and will need its own decision record.
