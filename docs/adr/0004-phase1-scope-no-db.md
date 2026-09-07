# 0004. Phase 1 scope: one collector proof of concept, no database

## Status

Accepted

## Context

The long-term ingestion architecture involves multiple independent
per-chain collectors feeding a validation and normalization pipeline that
ultimately writes into PostgreSQL. Building all of that at once, before a
single real data source has actually been fetched and inspected, risks
designing storage and validation rules around assumptions rather than
observed reality. In particular, the project has explicitly deferred
choosing a price-history storage strategy (full snapshots vs.
change-based history) until real dataset size and update characteristics
from a first supermarket are known.

## Decision

Phase 1 will implement exactly one independent supermarket collector as a
proof of concept, covering the full pipeline shape end-to-end but scoped
narrowly:

1. Fetch data from one approved official/public supermarket data source.
2. Persist the raw response/file as-is.
3. Apply minimal parsing to turn the raw format into an in-memory
   representation.
4. Validate the parsed data (e.g. required fields present, parseable,
   plausible record count/prices) before it is treated as usable.
5. Normalize the validated data into a normalized internal representation
   (in-memory / plain data structures).
6. Cover the above with automated tests.

Phase 1 explicitly does not include PostgreSQL, a database schema, or any
persistence beyond raw-file storage. This keeps the first collector focused
on proving the fetch -> parse -> validate -> normalize shape against a real
source, and defers schema and persistence decisions until they can be
informed by that real data.

## Consequences

- A second collector cannot be built in Phase 1; Phase 1's purpose is to
  validate the shape of a single collector, not to reach multi-chain
  coverage.
- Database schema design (including the price-history strategy) is
  deferred to a later phase, once real record counts, update frequency, and
  field variability are known from the Phase 1 collector.
- The normalized internal representation produced in Phase 1 should be
  designed so that persisting it later (once a schema exists) is a natural
  next step, but Phase 1 itself must not implement that persistence.
