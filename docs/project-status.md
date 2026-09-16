# Project Status

Current-state snapshot. This document summarizes the recorded history in
[`docs/work-log.md`](work-log.md). If it conflicts with the log, re-check
the underlying evidence and authorized decisions, append a correction
where needed, and update this summary. Neither document overrides actual
code, test evidence, or explicit authorized decisions, and neither
converts a hypothesis or open question into a requirement.

**Inspected base commit:** `6db56ea1f7acbbf7dd2282717be8dcbdc89a391a`
(branch `main`), per the inspection recorded as entry WL-0002 in
[`docs/work-log.md`](work-log.md).
File references below are relative to the repository root at that commit.

---

## 1. Repository facts (verified against source)

### Implemented and tested, standalone

| Component | Path | Evidence |
|---|---|---|
| Shufersal collector (discovery/download/transport/parse/validate/run) | `src/smartcart/collectors/shufersal/` | `tests/collectors/shufersal/` |
| Rami Levy collector, dual schema-family aware (ADR 0007) | `src/smartcart/collectors/rami_levy/` | `tests/collectors/rami_levy/` |
| Frozen normalized price-item contract (v1, 11 fields) | `src/smartcart/normalize/contract.py` | referenced by both normalizers |
| Shufersal/Rami Levy → common normalized contract | `src/smartcart/normalize/shufersal.py`, `rami_levy.py` | `tests/normalize/test_shufersal_normalize.py`, `test_rami_levy_normalize.py`, `test_rami_levy_standard_normalize.py` |
| Promotions normalization contract and mapping | `src/smartcart/normalize/promotion.py`, `promotion_contract.py` | `tests/normalize/test_promotion_normalize.py` |

### Integrated (cross-module import exists), not orchestrated

| Component | Path | Evidence |
|---|---|---|
| Normalize → persistence seam (resolves store, delegates to activation) | `src/smartcart/integration/occurrence_activation.py` | Only caller found repo-wide: `tests/db_spike/test_normalized_occurrence_activation.py` |

No module anywhere in `src/smartcart` calls a collector's `run.py` and
feeds its output through `normalize` into this seam. **No complete
collector → actual normalization → persistence test path was found in the
inspection performed. Indirect paths through helpers/fixtures remain
unverified; the originally approved scope of such coverage also remains
unverified. Existing DB tests are present.** (This supersedes the stronger
absence claims previously stated here and in `docs/work-log.md` WL-0002;
see WL-0009, WL-0016, and WL-0019.) The inspected test files exercise
these three connections separately:
collector fetch → Round 1 raw persistence
(`tests/db_spike/test_real_output_acceptance.py`, live-network-gated, not
using `normalize`); collector-record-shaped input → a `normalize` function
(`tests/normalize/test_shufersal_normalize.py`, `test_rami_levy_normalize.py`,
`test_rami_levy_standard_normalize.py`); and a synthetic
`NormalizedPriceItem` → `activate_normalized_occurrence` → Round 2
persistence (`tests/db_spike/test_normalized_occurrence_activation.py`).
No test file imports both a real `normalize.*` function and
`smartcart.integration.occurrence_activation`. There is no CLI or
application entry point in this package (no
`argparse`/`click`/`sys.argv`/`if __name__` anywhere under `src/smartcart`).

**Open verification question (owner-raised, unresolved — not a confirmed
gap):** whether a connected collector → actual `normalize` function →
persistence test might exist via a helper function or fixture not caught
by the direct-import check above, and whether such end-to-end coverage was
within the originally approved scope for this work. The existing DB-spike
tests (concurrency, crash recovery, etc.) are not in dispute — this
question is specifically about the collector→normalize→persistence
connection. The import-list check above is accurate for what it checked,
but does not rule out an indirect path through a shared helper/fixture
that doesn't show up as a top-level `from smartcart.normalize import ...`
statement. Recorded here as an open question pending investigation, not as
a confirmed implementation omission; investigating it is explicitly out of
scope for this documentation-only round (see `docs/work-log.md` WL-0016).

### Experimental spikes — explicitly not production infrastructure

| Component | Path | Status per own documentation |
|---|---|---|
| Focused DB Spike: Chain/Store/Content/Occurrence/Activation persistence | `src/smartcart/db_spike/` | `src/smartcart/db_spike/__init__.py`: "a correctness-of-mechanism experiment, not the final SmartCart persistence layer" (ADR 0009) |
| Crash-durability spike: content-addressed blob store + staging | `src/smartcart/durability_spike/` | ADR 0010 title: "temporary crash-safety infrastructure"; zero cross-imports with `collectors`, `normalize`, or `db_spike` |

Ordered/atomic/idempotent activation (`activate_occurrence`,
`src/smartcart/db_spike/activation.py`) and its concurrency/crash-recovery
tests (`tests/db_spike/test_activation_concurrency.py`,
`tests/durability_spike/test_crash_durability.py`) exist and describe real
PostgreSQL-backed locking and deterministic fault injection — this document
does not claim these tests currently pass; no test run is recorded for this
checkpoint (see §4).

### Not implemented / not present

- No application-level orchestration/CLI entry point (any channel).
- Promotions XML parsing, Promotions persistence, and basket/shopping-list
  functionality.
- Legacy backfill of normalized facts onto pre-existing rows (ADR 0011 §2 —
  deliberately deferred pending evidence, not an oversight).
- Partial/item-level activation acceptance (ADR 0011 §1 — deliberately
  deferred pending evidence).
- Product Identity resolution — within-retailer continuity and/or
  cross-retailer matching (see §3).
- Any app, API, WhatsApp, UI, wireframe, or product-flow artifact.
- Any roadmap document or recon-report file.

### Approved decisions (ADRs, all `Status: Accepted`)

0001 Python 3.12 target · 0002 channel-independent core · 0003 no
third-party scraper/parser code · 0004 Phase 1 scope, one collector PoC, no
DB · 0005 dependency licensing policy · 0006 Rami Levy provider endpoint ·
0007 Rami Levy dual source-schema families · 0008 collector-to-persistence
boundary · 0009 focused DB spike scope/boundary · 0010 crash-durability
spike scope · 0011 normalize-to-persistence seam failure handling, legacy
backfill, and contract provenance. Full text: [`docs/adr/`](adr/).

An ADR being `Accepted` records that the decision was approved; it does not
by itself mean the feature it scopes is finished, or that a later module
touching the same area was itself separately approved (see §3).

---

## 2. Owner-confirmed direction (relayed context, not code evidence)

The owner has confirmed the primary user-facing product direction is an
**Android/iOS application**, with a **complementary WhatsApp bot running
in parallel**. The owner selected platforms (Android and iOS), not a
native-versus-cross-platform technology choice — no framework, library, or
implementation technology is implied by this direction. As of the inspected commit, **no code for
either the app or the bot exists in this repository**; this is direction
recorded for planning purposes, not an implementation status. ADR 0002
(channel-independent core) remains the relevant architectural decision —
it predates this specific direction but is compatible with it.

---

## 3. Product Identity — resumed (owner-authorized, relayed)

**Status: resumed.** Product Identity was owner-authorized to resume
outside this Claude Code session's prior activity. This session did not
witness the resumption decision, the evidence/recon review, or the
Requirements Freeze directly — they are recorded as **owner-authorized,
relayed reviewed state**, per `docs/work-log.md` WL-0028/WL-0029, not as
something this session independently verified beyond what is stated
below. A Requirements Freeze now exists as relayed reviewed state (see
below); this supersedes the prior "no final freeze exists" wording, which
described an earlier, since-superseded checkpoint.

**Current execution state (Slice A):**
- **Batch A is complete.** Frozen scope PID-T01/PID-T02, **[relayed]** as
  independently reviewed and approved COMPLETE; the implementation itself
  is **[source]**-verified below.
- **Batch B is complete.** Frozen scope PID-T03, PID-T04, PID-T05 (A/B/C),
  PID-T38, plus two schema-boundary FK guards — all **[exec]**-confirmed
  GREEN this session (`tests/db_spike/test_product_identity_foundation.py`:
  10 passed; `tests/db_spike/test_migrations.py`: 3 passed; full
  `tests/db_spike` regression: 82 passed, 3 pre-existing skipped; ruff and
  mypy both pass). Migration 0006
  (`src/smartcart/db_spike/migrations/0006_product_identity_current_assignment.sql`)
  now exists, and `assign_chain_product()`/`product_assignment()` are
  implemented. Independent completion review approved Batch B subject to
  one targeted migration-comment wording correction (applied; no
  schema/behavior change) — **[relayed]** for the review verdict itself,
  **[source]**/**[exec]** for the correction and its re-verification. See
  `docs/work-log.md` WL-0031 for full detail.
- **Batch C is complete.** Frozen scope PID-T39, PID-T41, PID-T42,
  PID-T50, PID-T53, written tests-first (`docs/work-log.md` WL-0032) and
  independently reviewed as RED (PID-T39/T50) / GREEN characterization
  (PID-T41/T42/T53) before implementation began. `set_product_display_name()`
  is now implemented — **[source]**, direct read of
  `src/smartcart/db_spike/product_identity.py` — as exactly one SQL
  `UPDATE smartcart_product SET display_name = ... WHERE product_id = ...`;
  it does not touch `chain_product_current_assignment` or any retailer/
  source `product_name` evidence. All 15 Product Identity tests pass;
  full `tests/db_spike` regression: 87 passed, 3 pre-existing skipped;
  ruff and mypy both pass — all **[exec]**-confirmed this session.
  Independent completion review: "APPROVE BATCH-C COMPLETE — PROCEED TO
  DOCUMENTATION CHECKPOINT" — **[relayed]**. No new schema or migration.
  No naming algorithm, Display Name history, or NULL/removal semantics
  were introduced. Behavior for a nonexistent `product_id` remains
  deliberately unspecified. Full detail: `docs/work-log.md` WL-0033.
- **Slice B is complete.** Architecture and test-contract freeze
  (`docs/work-log.md` WL-0034) followed by tests-first work, independent
  RED review, minimal implementation, and independent completion review
  — **[relayed]** for both review verdicts, **[source]**/**[exec]** for
  the implementation and its verification. Full detail below and in
  `docs/work-log.md` WL-0035.
- **No Product Identity commit or push has been authorized.**
- Full detail, per-fact provenance: `docs/work-log.md` WL-0028
  (resumption, evidence/recon, Requirements Freeze, TDD planning), WL-0029
  (Batch A complete / Batch B RED-reviewed state, as it stood then),
  WL-0030 (this session's two Batch-B test-contract correction rounds),
  WL-0031 (Batch-B completion: implementation, final GREEN verification,
  completion-review outcome, and the concurrency limitation recorded
  below), WL-0032 (Batch-C tests-first contract freeze, and the
  `product_name` source-fact correction), WL-0033 (Batch-C completion:
  `set_product_display_name()` implementation, final GREEN verification,
  completion-review outcome, and the PI-17/PI-18/PI-19 boundaries
  recorded below), WL-0034 (Slice-B architecture and tests-first contract
  freeze), and WL-0035 (Slice-B completion: migration 0007,
  `correct_chain_product_assignment()` implementation, final GREEN
  verification including the non-vacuous atomicity proof, and the
  completion-review outcome).

**What is actually implemented, verified against source:**
- `smartcart_product` (`src/smartcart/db_spike/migrations/0005_product_identity_slice_a.sql`):
  `product_id bigserial PRIMARY KEY`, `display_name text` (nullable, not
  unique) — a SmartCart-owned Product identity, independent of any
  retailer tracking identity. `create_product(conn)`
  (`src/smartcart/db_spike/product_identity.py`) persists this row and
  requires no chain/item_code_raw input. This is the SmartCart Product's
  own `display_name` column — a separate concern from
  `store_product_current_state.product_name` (added by migration
  `0004_normalized_current_state_facts.sql`, store-scoped, overwritten on
  every new activation for the same key, no `FOREIGN KEY` to
  `smartcart_product`), which this schema does not treat as SmartCart
  Display Name. **Source-fact correction:** an earlier read-only
  reconciliation this session incorrectly stated no such retailer
  `product_name` field exists anywhere in this schema; it does, as just
  described — retracted, see `docs/work-log.md` WL-0032.
- `chain_product` (`src/smartcart/db_spike/migrations/0001_initial_schema.sql:140-143`):
  `PRIMARY KEY (chain_id, item_code_raw)` — chain-wide, not store-scoped —
  populated by `upsert_chain_product()`
  (`src/smartcart/db_spike/catalog.py:167-180`), which stores
  `item_code_raw` exactly as the retailer represents it and does nothing
  beyond `ON CONFLICT (chain_id, item_code_raw) DO NOTHING`: it registers
  that a code has been seen under a chain, nothing more. This is the
  Retailer Tracking Identity the Requirements Freeze (WL-0028) keeps
  explicitly distinct from the SmartCart Product ID above.
- `store_product_current_state` and `price_history`
  (migration 0001, lines 153-188) key price observations by
  `(chain_id, store_id, item_code_raw)` — store-scoped price tracking
  under that same raw code.
- `store`/`store_source_alias` (`src/smartcart/db_spike/catalog.py:59-148`)
  resolve a raw retailer store identifier to an opaque SmartCart `store_id`
  via an alias table — this is **Store** identity, a separate concern from
  product identity.
- `chain_product_current_assignment`
  (`src/smartcart/db_spike/migrations/0006_product_identity_current_assignment.sql`):
  the current, authoritative assignment of a Tracking Identity to a
  SmartCart Product ID — `chain_id`, `item_code_raw`, `product_id`;
  `PRIMARY KEY (chain_id, item_code_raw)`; `FOREIGN KEY (chain_id,
  item_code_raw) REFERENCES chain_product`; `FOREIGN KEY (product_id)
  REFERENCES smartcart_product`; no `UNIQUE(product_id)` — no history,
  timestamps, or candidate/resolver/source-name fields. No assignment row
  means UNRESOLVED. `assign_chain_product()`/`product_assignment()`
  (`src/smartcart/db_spike/product_identity.py`) implement this: first
  assignment persists; an identical repeat is an idempotent no-op; a
  conflicting reassignment (a different `product_id` for the same
  Tracking Identity) raises `ValueError` and leaves the existing
  assignment unchanged; `product_assignment()` is read-only and returns
  `None` when UNRESOLVED. `set_product_display_name()` **is implemented**
  (Batch C, `docs/work-log.md` WL-0033): exactly one `UPDATE
  smartcart_product SET display_name = ... WHERE product_id = ...` for an
  existing Product — it does not touch `product_id`,
  `chain_product_current_assignment`, or any retailer/source
  `product_name` evidence, and introduces no naming algorithm, no
  Display Name history, and no NULL/removal semantics. Preserved
  boundaries (relayed identifiers, WL-0033): **PI-17** SmartCart Product
  ID remains durable and independent of naming; **PI-18** Display Name is
  not identity; **PI-19** retailer source `product_name` remains separate
  from SmartCart Display Name.
- `chain_product_assignment_history`
  (`src/smartcart/db_spike/migrations/0007_chain_product_assignment_history.sql`):
  append-only history of superseded `chain_product_current_assignment`
  rows (H1) — `assignment_history_id bigserial PRIMARY KEY`, `chain_id`,
  `item_code_raw`, `product_id`, `superseded_at`; `FOREIGN KEY (chain_id,
  item_code_raw) REFERENCES chain_product`; `FOREIGN KEY (product_id)
  REFERENCES smartcart_product`; no additional `UNIQUE` constraint; no
  reason/source/actor/confidence/candidate fields; no valid_from/valid_to
  or bitemporal modeling. Each row represents the Product a Tracking
  Identity's assignment was corrected *away from* — never a dual-sided
  correction event carrying both the old and new Product ID.
  `correct_chain_product_assignment()`
  (`src/smartcart/db_spike/product_identity.py`) implements this: no
  current assignment for the Tracking Identity raises `ValueError`
  (correction is not a first assignment — that remains
  `assign_chain_product()`'s responsibility); a request for the
  already-current Product is an idempotent no-op with no history row; a
  genuine correction appends the superseded Product to history and
  updates the current assignment, atomically (both happen inside one
  `transaction()` block, or neither does — **[exec]**-confirmed
  non-vacuously this session via a temporary, standalone trace, see
  `docs/work-log.md` WL-0035). `assign_chain_product()`,
  `create_product()`, `set_product_display_name()`, and
  `product_assignment()` are unchanged — confirmed byte-identical by
  direct read. Display Name, retailer/source current-state evidence, and
  `chain_product`/`smartcart_product` themselves are never touched by a
  correction. Behavior for a requested `product_id` that does not exist
  is **not** part of this Slice-B contract — whatever the database's own
  FK constraint produces for that case is not a documented API
  guarantee.
- **Concurrency limitation — recorded as a known future concern, not a
  current blocker:** `assign_chain_product()` uses a transactional
  SELECT-then-INSERT. The frozen Batch-B contract did not define
  concurrent first-writer semantics; under concurrent writers, the
  database's own primary-key constraint may reject one writer, rather
  than the API providing a deliberately specified concurrency-level
  idempotency contract. No locking, `ON CONFLICT`, retry behavior, or
  other mechanism has been chosen — that design question is explicitly
  open for a future, separately authorized stage (see `docs/work-log.md`
  WL-0031).

**Requirements Freeze conclusions — [relayed], per `docs/work-log.md`
WL-0028:** `(chain_id, item_code_raw)` is Retailer Tracking Identity, not
SmartCart Product identity; SmartCart owns a durable Product ID;
UNRESOLVED is a valid state; cross-retailer many→one assignment is
allowed; **same-retailer concurrent many→one remains UNKNOWN** — the
freeze does not assert it either way, and PID-T38 was specifically
corrected to test only the cross-retailer case rather than assert
anything about the same-retailer case; assignment must be historically
correctable (deferred to Slice B at the time of this freeze — Slice B is
now COMPLETE, see above); Display Name is not identity; source
evidence remains distinct; a semantic-comparability boundary exists; a
zero-or-one authoritative current assignment exists; resolver/history/
naming/comparison architecture remains deferred.

**What this does and does not establish:** the Requirements Freeze settles
the policy questions listed above; it does not itself implement a
resolver, and it does not resolve real-product continuity mechanically —
no code anywhere yet resolves or asserts that a given `(chain_id,
item_code_raw)` observed over time is the same real-world product. If a
retailer reassigns or reuses an `item_code_raw` value, or changes a
product's declared quantity/name under an unchanged code, no mechanism
yet detects or represents that (ADR 0011 §6 already flags the related
gap: no normalized quantity/name history exists, only raw-evidence
replay).

**Open questions (unresolved, not to be treated as decided):**
- Whether/how to resolve real-product continuity under a stable or
  changing `(chain_id, item_code_raw)` key over time, within one retailer
  — resolver/history architecture remains deferred (see the deferred
  items listed in `docs/work-log.md` WL-0029 item F).
- **Same-retailer concurrent many→one remains explicitly UNKNOWN** — the
  Requirements Freeze allows cross-retailer many→one but does not decide
  the same-retailer case either way.
- External-data reconnaissance for cross-retailer/global identity: a
  retailer evidence/recon pass, a broad frozen 46-identifier sample, and
  an Open Food Facts pass are now **[relayed]** as performed (WL-0028); a
  GS1 accessibility attempt produced 0 successful per-identifier queries,
  so **GS1 identifier evidence remains UNKNOWN** — not established either
  way.
- What identifier-change semantics apply when a retailer changes an item
  code, a product's declared quantity, or its name over time — flagged as
  open in ADR 0011 §6 and among the deferred items in WL-0029 item F.

Do not close any of the above merely because related work has occurred —
closing any of them requires an explicit, separately approved decision.

**Continuation point:** Product Identity → Slice A **COMPLETE** (Batch A,
Batch B, Batch C) → Slice B architecture freeze APPROVED → Slice B
test-contract freeze APPROVED → Slice B tests-first, independently
RED-reviewed → **Slice B COMPLETE**. Next Product Identity scope requires
its own explicit review and authorization before new implementation
begins. This documentation checkpoint does not itself authorize any
further implementation, any migration/schema change, or any commit/push.

**Slice B — COMPLETE — [relayed] for both review verdicts,
[source]/[exec] for the implementation, per `docs/work-log.md` WL-0034
(architecture/test-contract freeze) and WL-0035 (completion; full detail
there):** the separate public correction seam,
`correct_chain_product_assignment(conn, *, chain_id: str, item_code_raw:
str, product_id: int) -> None`, is implemented — `assign_chain_product()`'s
existing semantics are unchanged (confirmed byte-identical by direct
read). History representation is **H1**, implemented: correction A→B
preserves A as superseded history; current state then contains B — the
append-only `chain_product_assignment_history` table
(`assignment_history_id` PK, `chain_id`/`item_code_raw`/`product_id`,
`superseded_at`; FK to `chain_product`; FK to `smartcart_product`), not a
correction-event record containing both IDs. `superseded_at` is an
approved architecture choice — PI-10 does not logically mandate a
wall-clock timestamp. A→A is an idempotent no-op with no history row;
correction with no current assignment raises `ValueError` (message not
frozen); correction is atomic (history-persist and current-update
together inside one `transaction()` block, or neither — proven
non-vacuous this session, WL-0035). Target-`product_id`-not-found
behavior remains **not defined** by this contract — no explicit
validation or new exception was added for it. No public history-read API
was added. Reason/source/actor fields, resolver/candidate/confidence
behavior, and same-retailer many→one remain deferred/UNKNOWN, unaffected
by Slice B's completion. **Requirements reopen: NO.**

All 9 frozen Slice-B pytest items are GREEN (PID-T07's two-correction
A→B→C append-only proof reached both corrections and every final
assertion; PID-T40; GUARD-NO-CURRENT; GUARD-NOOP; both GUARD-ATOMICITY
cases, independently confirmed non-vacuous via a temporary trace outside
the repository; three history PK/FK guards), plus the two migration-test
modifications, all GREEN. Full Product Identity suite: 24 passed, 0
failed. Migration tests: 3 passed, 0 failed. Full `tests/db_spike`
regression: 96 passed, 3 pre-existing skipped, 0 failed. ruff and mypy
both pass. Independent completion review: "APPROVE SLICE-B COMPLETE —
PROCEED TO DOCUMENTATION CHECKPOINT."

**Still excluded / deferred (unchanged in substance, carried forward from
WL-0029 item F, the concurrency limitation above, and the explicit
Batch-C/Slice-B exclusions in WL-0032/WL-0033/WL-0034/WL-0035 — none of
these were introduced or closed by Slice B's completion):** resolver/
matcher; candidate/confidence model; GTIN verification/authority; product
continuity/family/successor model; Display Name generation algorithm/AI
naming/translation-localization; Display Name removal/`NULL`-transition
semantics; source-name history across successive observations;
concurrency/locking semantics for assignment writes (the concurrency
limitation recorded above for `assign_chain_product()` is **not** solved
by Slice B's atomicity guarantee, which covers only
`correct_chain_product_assignment()`'s own two-write sequence); a public
assignment-correction-history UI/API; operational merge/split tooling; an
explicit target-product-not-found contract. **Same-retailer concurrent
many→one remains UNKNOWN**, unaffected by Batch C or Slice B.

**Stale, non-blocking test-comment debt (recorded, not fixed this
round):** `tests/db_spike/test_activation_normalized.py`'s module
docstring still claims `NormalizedActivationItem`/`normalized_items` are
unimplemented; they are not — see `docs/work-log.md` WL-0033. This is
documentation/test-comment debt, not a Batch-C defect, and does not block
anything; future cleanup, out of this checkpoint's authorized scope.

---

## 4. Current stopping point, next action, missing approvals

**Stopping point:** a further minimal correction round has been applied —
a transcript-labeling and command-count correction to `docs/work-log.md`
WL-0017, and replacement of the categorical
collector→normalize→persistence test-path absence claim in `README.md`
and this document with an evidence-scoped statement (existing DB tests
unaffected; indirect helper/fixture paths and originally approved scope
remain unverified, per the WL-0016 open question) — with the
corresponding entries appended to `docs/work-log.md`. **None of it has
been reviewed or approved, and no commit or push has been made.**
Separately, a documentation coverage/evidence matrix and gap list has been
authored at [`docs/documentation-coverage.md`](documentation-coverage.md),
inventorying what a new session needs before the full handover package
(`start-here.md`, `product-vision.md`, `roadmap.md`, `architecture.md`,
`testing-map.md`, `database-map.md`, `research-and-open-design.md`,
`environment.md`, `glossary.md`, `constraints.md` — all currently
planned, none yet authored) can be written, and where the supporting
evidence for each already exists. This is explicitly separate from, and
does not require or substitute for, the pending commit/push authorization
above. A further correction round has since applied targeted fixes to the
coverage matrix itself and recorded the checkpoint's approval state
explicitly (see [`docs/documentation-coverage.md`](documentation-coverage.md)
§1.1 and `docs/work-log.md` for this round's entries).

**Approval state, stated without conflating content approval with Git
authorization:**

**The five-file documentation checkpoint, as reviewed through WL-0021,
received content approval from GPT and Claude Chat, relayed through the
owner. Coverage-matrix work and subsequent edits beginning with WL-0022
require their own review. Commit and push remain separately
unauthorized.**

- **Content approval** — covers the checkpoint's content as it stood
  through `docs/work-log.md` WL-0021 (every correction round up to and
  including the WL-0021 wording adjustments). This is content approval
  only, relayed through the owner and confirmed this round by Claude
  Chat's own direct check of its earlier closing verdict (see
  `docs/work-log.md` WL-0026); it is not a Git-authorization decision.
- **Coverage-matrix work and subsequent edits (WL-0022 onward)** — each
  still requires its own review; content approval through WL-0021 does
  not extend to them. This correction does not itself approve the
  current coverage matrix or any later edit.
- **Approved scope for preparing corrections** — granted, for the
  documentation files this and the prior rounds named.
- **Commit authorization** — not given; content approval of the
  checkpoint's text is a separate matter from authorization to `git
  commit` it, and neither preparing corrections under an approved scope
  nor the content approval above implies it (`docs/development-workflow.md`
  §4).
- **Push authorization** — not given; separate again from commit
  authorization.

**Correction to a prior mischaracterization here:** an earlier version of
this section stated that every correction round since WL-0007 "still
requires its own review," implying WL-0007 through WL-0021 were
unapproved. That was inaccurate — those rounds are covered by the content
approval above. The accurate boundary is the one stated at the top of
this subsection: approved through WL-0021; not yet reviewed from
WL-0022 onward. See `docs/documentation-coverage.md` §1.1 for the
identical correction and `docs/work-log.md` WL-0026 for the relayed
confirmation supporting it.

**Next proposed action:** none is authorized yet for this five-file
documentation checkpoint/coverage-matrix track — task selection and scope
for whatever comes next in that track require agreement before execution,
per [`docs/development-workflow.md`](development-workflow.md) §1. This
document does not propose one on its own authority. Product Identity is a
separate track: it has been owner-authorized to resume (§3,
`docs/work-log.md` WL-0028), and Slice A (Batch A, Batch B, Batch C) and
Slice B are all complete (§3, WL-0031/WL-0033/WL-0035) — its own next
required approval is stated in §3 above (explicit review/authorization
before any further Product Identity implementation scope begins), not
this bullet.

**Missing approvals:**
- Review of every documentation diff from WL-0022 onward (the coverage
  matrix and every correction round to it since, including this one) —
  not WL-0007 onward, which is covered by the content approval above.
- Explicit authorization to `git commit` the approved files (which, once
  given, covers staging them as part of that same authorization — there is
  no separate staging-approval gate; see `docs/development-workflow.md` §4).
  Content approval of the checkpoint's text (above) does not, by itself,
  supply this.
- A separate, explicit authorization to `git push`.
- Product Identity: **resumption is owner-authorized (relayed, §3), and
  Slice A (Batch A, Batch B, Batch C) and Slice B are all complete (§3,
  WL-0031/WL-0033/WL-0035)** — none of that is a missing approval. What
  remains missing for that track: explicit review/authorization before
  any further Product Identity implementation scope (resolver/matcher,
  candidate/confidence model, GTIN, naming generation, a public
  correction-history UI/API, operational merge/split tooling, or the
  recorded concurrency limitation) begins; no Product Identity commit or
  push has been authorized either.

This summary does not override the underlying code, test evidence, or an
explicit authorized decision. A contradiction between this summary and
either of those — or between this summary and an earlier
`docs/work-log.md` entry — is resolved by re-checking the evidence and
recording a correction entry, never by treating this summary or an earlier
log entry as automatically correct (see `docs/work-log.md` Conventions).

**Work-log references:** WL-0001 (mechanism baseline) · WL-0002
(repository inspection — its collector→normalize→persistence claim is
corrected by WL-0009) · WL-0003 (addendum verification — no prior
checkpoint found; its characterization is corrected by WL-0006) · WL-0004
(five-file checkpoint created) · WL-0005 (owner workflow clarification) ·
WL-0006 (WL-0003 characterization correction) · WL-0007 (correction round
received) · WL-0008 (platform/identity/gates/status corrections applied) ·
WL-0009 (test-path evidence correction) · WL-0010 (process note: WL-0006
was applied, not only proposed) · WL-0011 (durable check-result log — its
verbatim-output claim is corrected by WL-0015) · WL-0012
(consistency-check findings, reported not applied) · WL-0013 (this
targeted-correction round received) · WL-0014 (README/project-status
corrections applied) · WL-0015 (WL-0011 provenance correction and bounded
verbatim-claims check) · WL-0016 (open test-coverage question recorded) ·
WL-0017 (this round's actual documentation-check outcomes) · WL-0018
(WL-0017 transcript-label and command-count correction) · WL-0019
(test-path absence claim superseded with evidence-scoped wording in
`README.md` and this document) · WL-0020 (this round's stopping point and
validation checks) · WL-0021 (final wording adjustments to the WL-0019
test-path text) · WL-0022 (documentation coverage/evidence matrix task
received; inspection performed) · WL-0023
(`docs/documentation-coverage.md` authored; this update) · WL-0024
(coverage-matrix corrections and source-transfer-list round received) ·
WL-0025 (approval-state, roadmap, research-coverage, ADR-citation, and
completeness-checklist corrections applied) · WL-0026 (approval-chronology
mistake identified and corrected: content approval covers through
WL-0021, not just WL-0007 onward as unapproved) · WL-0027
(source-transfer availability split and GS1/Open Food Facts wording
correction applied) · WL-0028 (Product Identity resumption, evidence/
recon, Requirements Freeze, and TDD planning — owner-authorized, relayed)
· WL-0029 (Product Identity Slice A Batch A complete / Batch B RED
reviewed, as it stood then — mixed provenance, labeled per fact) ·
WL-0030 (Batch-B test-contract correction rounds witnessed directly by
this session) · WL-0031 (Product Identity Slice A Batch B COMPLETE:
implementation, final GREEN verification, completion-review outcome, and
the concurrency limitation recorded as a future concern) · WL-0032
(Product Identity Slice A Batch C tests-first contract freeze —
PID-T39/T41/T42/T50/T53, reviewed/relayed; and the
`store_product_current_state.product_name` source-fact correction) ·
WL-0033 (Product Identity Slice A Batch C COMPLETE:
`set_product_display_name()` implementation, final GREEN verification,
independent completion-review outcome, the PI-17/PI-18/PI-19 boundaries,
and the stale `test_activation_normalized.py` docstring recorded as
separate non-blocking debt) · WL-0034 (Product Identity Slice B
architecture freeze and tests-first contract freeze — the
`correct_chain_product_assignment()` seam, H1 append-only history
representation, the 9 frozen new pytest items, and the two existing
migration-test modifications; Slice B not yet implemented as of that
entry) · WL-0035 (Product Identity Slice B COMPLETE: migration 0007,
`correct_chain_product_assignment()` implementation, final GREEN
verification including the non-vacuous atomicity proof, and the
independent completion-review outcome; this update).
See
[`docs/work-log.md`](work-log.md) and
[`docs/documentation-coverage.md`](documentation-coverage.md).

## 5. T13 — Occurrence fact immutability (Owner-approved, relayed)

The Owner has explicitly approved a system-wide invariant governing
`artifact_occurrence`, recorded as
[ADR 0011 §8](adr/0011-normalize-persistence-seam-failure-and-provenance.md)
(`docs/work-log.md` WL-0037, broadened by WL-0038):

- **Immutable historical facts:** every fact fixed when an occurrence is
  inserted -- `occurrence_id`, `content_id`, `ingestion_run_id`,
  `chain_id`, `store_id`, `artifact_kind`, `source_filename`,
  `schema_family`, `collected_at`, `validation_status`,
  `validation_detail`, `created_at` -- MUST NOT be changed afterward by
  any production code path. Any future schema column must be explicitly
  classified as an immutable fact or mutable operational metadata; it
  must not become mutable merely by omission from this list.
- **Mutable operational metadata, explicitly separate from the above:**
  `activation_completed_at` and `activation_outcome` remain mutable --
  `activate_occurrence()` continues to update only those two columns.
- **Routine occurrence deletion is prohibited** by this contract.
- **Corrections and revalidation must be additive,** through a new
  occurrence row or an explicit future correction/version mechanism (not
  yet designed or built); they must never rewrite historical facts in
  place or silently delete historical provenance.
- **Database-level enforcement is NOT part of this decision.** No trigger
  or constraint currently enforces any of the above; enforcement remains
  possible future work, requiring its own design and tests-first cycle.
  The correct characterization today is that mutation/deletion is
  contractually forbidden and that no current production writer performs
  it -- not that it is technically impossible.

**Two distinct gaps this track has now closed, kept separate because they
were resolved at different times by different scoped decisions:**
1. The **store-lock-order blocker** (whether `persist_normalized_
   occurrence_evidence()`'s pre-transaction, unlocked `store_id` read was
   safe) -- resolved by the earlier, narrower three-field decision
   (`chain_id`/`store_id`/`collected_at`, WL-0037).
2. The **activation-eligibility contract gap** (`activate_occurrence()`
   reading `artifact_kind`/`validation_status` unlocked, with no
   comparable binding contract behind those two specifically) -- resolved
   now by this broadened, Owner-approved general occurrence-fact
   invariant (Option C, WL-0038).

**Still open / not yet built:**
- **Documentation checkpoint:** this entire track -- the ADR decision, the
  three re-annotated production docstrings (`insert_occurrence()`,
  `activate_occurrence()`, `persist_normalized_occurrence_evidence()`),
  this section, and `docs/work-log.md` WL-0037/WL-0038/WL-0039 -- awaits
  independent technical/content review. That review is not an additional
  Owner authorization gate: `docs/development-workflow.md` §4 defines
  exactly two Owner authorization gates for this repository -- commit
  (given after diff review) and, separately, push (given after commit).
  The next Owner decision, once review succeeds, is whether to authorize
  the commit; push is a separate, later decision after that. Neither has
  been given; nothing in this track has been committed or pushed.
- **Database enforcement:** deferred, not built; no trigger or constraint
  exists yet.
- **Correction/revalidation mechanism:** an explicit open required
  precondition (ADR 0011 §8) that must be designed before rebuild,
  publication, or first real production ingestion -- none of those three
  may proceed against this mechanism's absence. This precondition remains
  open and unchanged by this round's process-wording correction.
- **GitHub issue (correction/revalidation prerequisite):** recommended, to
  track the open correction/revalidation-mechanism precondition ahead of
  rebuild, publication, or first production ingestion. Not created in this
  documentation-only round.
- **GitHub issue (database enforcement):** a separate, distinct piece of
  deferred future work -- recommended as its own issue, not combined with
  the correction/revalidation issue above. Not created in this
  documentation-only round.

Neither GitHub issue is required before, or a precondition for, committing
this documentation checkpoint itself; issue creation is expected to follow
the eventual commit/push of this checkpoint, not precede it.
