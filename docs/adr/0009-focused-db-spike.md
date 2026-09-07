# 0009. Focused DB spike: scope, module boundary, and driver/migration choice

## Status

Accepted

## Context

Architecture review has authorized a "Focused DB Spike": a correctness-of-
mechanism experiment proving that a relational model can support immutable
source evidence, Content/Occurrence separation, provenance preservation,
content deduplication, processing/activation idempotency, ordered
same-store activation, independent cross-store concurrency, atomic derived
state activation, `StoreProductCurrentState`, and append-oriented
`PriceHistory` -- using the real collector output contracts already
inspected against ADR 0008.

Two existing ADRs literally forbid the scaffolding this requires:

- ADR 0004 ("Phase 1 scope") states Phase 1 "explicitly does not include
  PostgreSQL, a database schema, or any persistence beyond raw-file
  storage."
- ADR 0008 ("Collector-to-persistence boundary") states "No `db/`,
  `persistence/`, `storage/`, `schema.py`, `connection.py`, `ingest.py`,
  `tests/db/`, or equivalent scaffolding should be created until
  DB/data-model design is complete."

This spike *is* the beginning of that DB/data-model design work, not its
completion -- it is explicitly not authorization to implement the final
production database. Proceeding without recording this tension would mean
silently working around both ADRs rather than making the exception
explicit and bounded, which is the failure mode ADR 0008 itself was
written to prevent.

A second piece of context this ADR must record: the DB driver and
migration mechanism were chosen only after checking what this repository's
actual environment can run. Neither PostgreSQL nor Docker is installed on
the development machine used for this work, and CI (`.github/workflows/
ci.yml`) does not currently provision one either. Rather than fall back to
SQLite -- which would not exercise real PostgreSQL transaction/locking
semantics and would undermine the spike's stated purpose of testing
ordered activation, atomic derived-state writes, and concurrency -- an
embedded, pip-installable real PostgreSQL binary (`pgserver`) is used to
run genuine PostgreSQL 16.2 without requiring a system install, Docker, or
a cloud vendor.

## Decision

**Scope of the exception.** ADR 0004's "no persistence beyond raw-file
storage" clause and ADR 0008's scaffolding-timing clause are narrowly
superseded, *only* for the bounded, explicitly-scoped Focused DB Spike
described above -- not as a general reopening of either ADR. ADR 0008's
substantive boundary rule is unaffected and remains fully in force:
collectors must never import or depend on this new module, and this new
module may depend on collector output types when justified.

**Module naming.** The spike lives in `src/smartcart/db_spike/` (and
`tests/db_spike/`), not `src/smartcart/db/`. The name is deliberately not
the eventual production name: it signals to any future reader -- even
after this ADR exists -- that the schema/module boundary here is a
provisional experiment, not a committed production design. Promoting this
work into a permanent module name is a separate future decision requiring
its own ADR once the schema is no longer expected to change based on
spike findings.

**DB driver: `pg8000` (runtime dependency).** `pg8000` is a pure-Python
PostgreSQL driver (DB-API-style, plus a `pg8000.native` convenience API
used here), BSD-3-Clause licensed. Alternatives considered:

- `psycopg` (v3): the most widely used PostgreSQL driver for Python, but
  licensed LGPL-3.0. Per docs/adr/0005, copyleft/ambiguous licenses
  require explicit discussion and sign-off rather than silent adoption;
  LGPL is a weak-copyleft license that is standard and low-risk for
  dynamically-linked/imported use in proprietary software (it does not
  require this project's own code to be open-sourced), but it is a
  license class ADR 0005 specifically asks to be flagged, not defaulted
  into, when a same-capability permissive alternative exists.
- `psycopg2`: same LGPL consideration as psycopg3, and is the older,
  less actively developed line.
- `pg8000` (chosen): BSD-3-Clause (permissive, matches ADR 0005's
  low-risk category with no flagging needed), pure Python (no compiled
  C-extension/libpq dependency to manage across Windows/Linux/WSL, which
  directly serves this project's stated portability goal), actively
  maintained, and sufficient for this spike's needs (parameterized
  queries, explicit transaction control via `BEGIN`/`COMMIT`/`ROLLBACK`,
  typed round-tripping of `bytea`/`numeric`/`timestamptz`). Its own
  transitive dependencies (`scramp`, `asn1crypto`, `python-dateutil`,
  `six`) are all permissively licensed (MIT/BSD/Apache-2.0 family).

This choice is specific to the spike; it is not a final production driver
decision, though it is production-capable and there is no known reason it
could not remain the production choice.

**Embedded PostgreSQL for tests/local dev: `pgserver` (dev-only
dependency).** `pgserver` (Apache-2.0) ships real PostgreSQL 16.2 server
binaries as pip-installable wheels for Linux, macOS, and Windows, and
provides `pgserver.get_server(data_dir)` / `.get_uri()` / `.cleanup()` to
start, connect to, and tear down a real, disposable PostgreSQL instance
with no admin rights, no Docker, and no system-wide install. This was
verified working end-to-end on this repository's actual development
machine (PostgreSQL 16.2 booted, `pg8000` connected, DDL/DML executed,
explicit transaction commit/rollback both verified) before being adopted.
It is used only in `tests/db_spike/` (and would be used identically in
CI, since it needs no service container); production database
provisioning is an explicit non-decision here (no cloud vendor is chosen;
see docs/adr/0008's still-open item list).

**Migration mechanism.** A minimal, hand-rolled, version-tracked SQL
migration runner (`db_spike/migrate.py` applying numbered `.sql` files
from `db_spike/migrations/`, recorded in a `schema_migrations` table) is
used instead of adopting a migration framework (e.g. Alembic). This adds
zero new dependencies beyond the driver already justified above, is
sufficient to "construct the database from an empty state reproducibly"
(the spike's actual requirement), and deliberately does not attempt
production zero-downtime migration concerns (multi-step
expand/contract, concurrent-safe DDL, rollback tooling), which are out of
scope for a spike per the round's own instructions.

## Consequences

- `src/smartcart/db_spike/` and `tests/db_spike/` now exist. Collectors
  (`src/smartcart/collectors/**`) must still never import from this
  module or vice versa in the collector-to-persistence direction; this
  remains verified by inspection, not yet by an automated architectural
  test (a future round may want one).
- `pg8000` becomes this project's first runtime dependency (previously
  `dependencies = []` in `pyproject.toml`); `pgserver` becomes a dev-only
  dependency used solely to make PostgreSQL-backed tests runnable without
  external infrastructure.
- This ADR does not decide: production database hosting/provisioning,
  final module naming/promotion, final migration framework for
  production-scale schema evolution, or whether `pg8000` remains the
  long-term driver. Each remains open.
- The schema produced by this spike is explicitly provisional. Round 2
  and later architecture review may change it; no downstream code should
  assume its field/table shapes are final.
