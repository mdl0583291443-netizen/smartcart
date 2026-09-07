-- 0002_round2_activation: Focused DB Spike Round 2 minimum additions.
--
-- Round 2 proves ordered, atomic, idempotent derived-state activation for
-- already-durable, valid, store-scoped ArtifactOccurrence rows (see
-- src/smartcart/db_spike/activation.py's module docstring). Only the two
-- additions strictly required for that are made here; no other Round 1
-- shape is changed.

-- Minimum durable occurrence-resolution state: answers "is there an
-- earlier ordered durable occurrence for this store that is still
-- unresolved?" without a generalized workflow/lifecycle table. NULL means
-- unresolved (not yet activated); non-null records when activation
-- completed, whether it applied derived-state writes or preserved the
-- occurrence as stale without mutating them -- both are terminal,
-- resolved outcomes for ordering purposes. There is deliberately no
-- separate "status" column: activation of a valid, store-scoped occurrence
-- has exactly two terminal shapes (applied, or preserved-stale), and
-- distinguishing them is not needed to answer the ordering question this
-- column exists for -- store_product_current_state/price_history rows
-- referencing the occurrence are themselves the durable record of which
-- shape occurred.
ALTER TABLE artifact_occurrence
    ADD COLUMN activation_completed_at timestamptz;

-- Durable database-enforced idempotency for the PriceHistory effect: an
-- occurrence may contribute at most one PriceHistory event per product it
-- observed. This is the uniqueness rule the round's governance describes
-- as UNIQUE(source_occurrence_id, chain_product_id), expressed with this
-- schema's existing chain-scoped product identity columns (chain_id,
-- item_code_raw) rather than inventing a chain_product_id surrogate that
-- does not otherwise exist here (chain_product's key is already the
-- composite (chain_id, item_code_raw)).
ALTER TABLE price_history
    ADD CONSTRAINT price_history_occurrence_product_unique
    UNIQUE (source_occurrence_id, chain_id, item_code_raw);
