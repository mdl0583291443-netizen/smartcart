# 0011. Normalize-to-persistence seam: failure handling, legacy backfill, and contract provenance

## Status

Accepted

## Context

Before writing the RED matrix for the normalize-to-persistence seam (which
projects `smartcart.normalize.contract.NormalizedPriceItem` into
`store_product_current_state` via an extended `activate_occurrence`, per the
prior requirements/invariants inspection), several architectural questions
needed a decision so the RED tests are not written against still-open
design: how activation failure is handled when normalized data is involved,
whether pre-existing `store_product_current_state` rows get backfilled, and
how a `NULL` normalized field on an old row is distinguished from a `NULL`
normalized field the retailer genuinely never provided. This ADR records
those decisions. It does not implement them.

## Decision

### 1. Partial acceptance / failure handling — deferred

Current behavior remains whole-occurrence conservative failure:
`activate_occurrence` either applies every item in an occurrence or none of
them, exactly as it does today. Partial, item-level acceptance is
deliberately **not** implemented in this slice.

**Reason.** Real retailer reconnaissance performed so far — approximately
35,553 PriceFull items across Shufersal, Rami Levy Standard, and Rami Levy
Online — has not produced an observed real item-level malformed-record case
sufficient to justify implementing partial acceptance. Inventing rejection
thresholds, a rejection-table schema, `PARTIALLY_APPLIED` semantics,
item-level recovery policy, or retry/replay workflow details now would be
designing against a case that hasn't been evidenced. These remain
evidence-driven future decisions.

The following **future architecture principles are frozen as documented
guidance now; only their implementation is deferred**:

- **(A)** A future source-local rejection may only be classified through
  deterministic, pre-registered, evidence-backed validation rules.
- **(B)** Never use generic exception catching to infer retailer/source
  fault.
- **(C)** Unknown/unclassified failures remain conservative SmartCart/system
  failures.
- **(D)** If future evidence justifies partial acceptance: valid items may
  be activated; proven malformed source-local items may be rejected; an
  existing rejected product's successful `CurrentState` value and provenance
  remain unchanged; a rejected *new* product gets no fabricated
  `CurrentState`; rejection information must be durably
  observable/investigable; raw source evidence remains preserved; and
  rejected-item handling must never falsely imply that an older value was
  observed in the newer occurrence.
- **(E)** Future failure handling should support the path: failure →
  processing-stage identification → source-evidence inspection → cause
  classification → SmartCart fix OR proven source-defect classification →
  replay/reprocessing where appropriate.
- **(F)** Future partial acceptance can compose additively with the
  existing one-transaction-per-occurrence atomicity model; it does not
  currently require redesigning activation atomicity. Therefore the
  normalize-to-persistence seam being built now must preserve the existing
  occurrence-level transaction boundary and must **not** introduce per-item
  transaction commits.

The exact future implementation of partial acceptance remains deliberately
unfrozen.

### 2. Legacy backfill — deferred pending evidence

The upcoming normalized-current-state migration adds `product_name`,
`declared_quantity`, `declared_quantity_raw`, `declared_quantity_unit_raw`,
and `is_weighted` to `store_product_current_state`. No legacy backfill is
performed in this slice.

This is **not** a permanent prohibition. Backfill/replay is deliberately
deferred until concrete product/operational evidence requires it. Existing
rows may therefore retain `NULL` normalized-fact fields indefinitely if the
product never receives another accepted observation — an acknowledged
limitation, not an oversight. Raw historical source evidence remains
preserved, so future replay/backfill remains possible, although potentially
expensive. Future successful observations through the new seam naturally
populate these facts for active products going forward.

### 3. Normalization contract provenance

A real ambiguity was identified: `is_weighted = NULL` on a
`store_product_current_state` row could otherwise mean either "a legacy row
where SmartCart never persisted normalized source facts" or "a successfully
normalized row where the retailer genuinely did not provide the weighted
flag." These two meanings must be distinguishable.

**Frozen requirement:** add one nullable integer provenance column to
`store_product_current_state`: `normalization_contract_version`.

- `NULL` = a legacy `CurrentState` row whose normalized source-fact fields
  were not populated through the normalize-to-persistence seam.
- `1` = the normalized source-fact fields were populated under the
  currently frozen `NormalizedPriceItem` v1 contract.

This field describes the `NormalizedPriceItem` **contract version** only.
It does **not** describe the DB schema/migration version, the retailer XML
schema version, the adapter implementation version, or the parser version.
The current frozen 11-field `NormalizedPriceItem` contract is version 1. No
general versioning framework, registry, compatibility layer, or semantic
versioning system is introduced; future contract versions are not designed
now.

**Database-domain requirement:** `normalization_contract_version` is
nullable; when non-null it must be `>= 1`.

### 4. Current-state write semantics

On a successful `APPLIED` write through the new normalized persistence
path: `product_name`, `declared_quantity`, `declared_quantity_raw`, and
`declared_quantity_unit_raw` are written; `is_weighted` is written exactly
according to the normalized source fact, including a legitimate
`None`/`NULL`; and `normalization_contract_version` is set to `1`. These
values describe one coherent normalized-contract projection and must be
written together with the occurrence's `CurrentState` activation, in the
same statement/transaction as the existing price columns.

On `STALE_PRESERVED` or `ALREADY_APPLIED`, none of these fields — including
`normalization_contract_version` — are mutated, exactly like every other
`store_product_current_state` column today.

### 5. Pre-mutation occurrence/item consistency guards

The normalize-to-persistence seam introduces three new consistency invariants, validated before any `CurrentState`/`price_history` mutation begins for an occurrence:

- **Chain agreement.** For every `NormalizedPriceItem` being persisted as part of an occurrence, `item.retailer_chain_id` must exactly equal the occurrence's `chain_id`.
- **Store agreement.** The raw retailer `store_id` continues to be resolved outside normalization through the existing store-alias mechanism (unchanged). The resolved SmartCart surrogate store ID used for persistence must exactly equal the occurrence's `store_id`.
- **`collected_at` agreement.** Every item's `collected_at` must exactly equal the occurrence's `collected_at`. No tolerance, normalization, rounding, or timestamp rewriting is permitted at this boundary.

A mismatch on any of these three is a seam/caller construction error, not a legitimate business state, and must cause the persistence attempt to fail rather than silently write inconsistent data.

These guards must be evaluated before mutation begins and must not introduce per-item transaction boundaries — the existing one-transaction-per-occurrence atomicity (§1(F), §4) is unchanged.

**Explicitly out of scope for these guards:** changes to the frozen `NormalizedPriceItem` v1 contract (no occurrence-context fields are added to it); redesign of store-alias resolution; partial acceptance; per-item commits; new failure-classification machinery. These remain governed by ADR 0011 §1 and §2 as already written.

### 6. Temporal limitation — quantity history

`store_product_current_state` stores the latest normalized source facts;
`price_history` remains price-only. This slice does not add normalized
quantity/name/`is_weighted` history. Historical changes such as
shrinkflation are therefore not directly queryable from any normalized
historical table yet — only reconstructable by replaying preserved raw
evidence. This is a deliberate, deferred gap, not accidental data loss (see
also the reverse-gap analysis in the prior normalize↔persistence inspection
and the requirements/invariants inspection that preceded this ADR).

### 7. What is frozen now vs. deferred

**Frozen now:**
- Current conservative whole-occurrence failure behavior (no partial
  acceptance).
- The classification safety principles (A)–(F) above.
- Occurrence-level atomicity must remain; no per-item transaction commits.
- Chain/store/`collected_at` agreement between each `NormalizedPriceItem`
  and its occurrence must be validated before mutation; a mismatch is a
  construction error, not a partial-acceptance case.
- No legacy backfill in this slice.
- `normalization_contract_version` semantics (nullable int; `NULL` = legacy,
  `1` = current contract version; `>= 1` when set; describes contract
  version only).
- Current-state normalized-field write semantics (§4).
- `price_history` remains price-only.

**Deferred / not frozen:**
- Rejection-report table/schema.
- Rejection thresholds.
- `PARTIALLY_APPLIED` or any alternative occurrence semantics.
- Detailed replay/retry workflow.
- Future `NormalizedPriceItem` contract versions (2+).
- Normalized quantity-history schema.
- Whether/when legacy backfill becomes necessary.

## Consequences

- The RED matrix for the normalize-to-persistence seam can now be written
  against a settled failure-handling and provenance model, without needing
  to invent partial-acceptance or versioning behavior it isn't evidenced to
  need yet.
- `store_product_current_state` will grow one additional provenance column
  (`normalization_contract_version`) beyond the five normalized source-fact
  columns already scoped by the prior requirements inspection — still
  purely additive, still nullable, no backfill.
- A future partial-acceptance design remains free to compose with the
  existing per-occurrence transaction boundary; nothing decided here
  forecloses that design, but nothing here designs it either.
- Legacy rows and genuinely-unweighted-by-retailer rows remain
  distinguishable indefinitely via `normalization_contract_version`, even
  though both may show `is_weighted IS NULL`.
- This ADR does not decide: rejection-table schema, replay/retry mechanics,
  the second `NormalizedPriceItem` contract version, quantity-history
  design, or a legacy-backfill trigger/threshold. Each remains open,
  evidence-driven future work.
