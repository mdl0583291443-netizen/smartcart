"""Focused DB Spike (Round 1): a correctness-of-mechanism experiment, not
the final SmartCart persistence layer.

See docs/adr/0009-focused-db-spike.md for why this module exists, why it
is named db_spike rather than db, and why pg8000/pgserver were chosen.
ADR 0008's collector-to-persistence boundary applies in full: nothing
under src/smartcart/collectors/ may import from this package, and this
package may depend on collector output types when justified.

Modules:
- db.py -- connection/DSN handling and explicit transaction control.
- migrate.py -- minimal version-tracked SQL migration runner.
- migrations/ -- numbered .sql migration files.
- content.py -- ArtifactContent persistence/dedup.
- occurrence.py -- ArtifactOccurrence persistence/provenance.
- catalog.py -- Chain/Subchain/Store/StoreSourceAlias/ChainProduct identity.
- activation.py -- minimal StoreProductCurrentState/PriceHistory shapes
  (no ordering/atomicity/idempotency enforcement yet -- see Round 2).
- ingestion_run.py -- IngestionRun envelope (not a transaction boundary).

Scope is deliberately Round 1 only: the minimum relational shape needed to
test canonical content identity, content/occurrence separation, raw
identity/alias preservation, and typed-vs-raw price coexistence. Ordered
activation, atomicity, concurrency, and idempotency enforcement are
explicitly deferred to Round 2.
"""
