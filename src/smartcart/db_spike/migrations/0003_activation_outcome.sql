-- 0003_activation_outcome: preserve which terminal shape an occurrence's
-- activation took, not just that it was resolved (Round 2 architecture
-- review correction).
--
-- Migration 0002 added activation_completed_at as the single durable
-- resolution marker, reasoning that ordering only needs resolved/
-- unresolved semantics. That collapses two historically distinct facts
-- -- "this occurrence's products were actually applied to CurrentState/
-- PriceHistory" vs. "this occurrence was preserved but never applied
-- because a later occurrence had already committed" -- into one
-- timestamp, losing the outcome permanently once written. This migration
-- adds it back as its own column, without touching the ordering
-- semantics (still governed entirely by activation_completed_at IS NULL
-- vs. NOT NULL).
--
-- Only the two terminal outcomes Round 2 can ever produce are
-- representable ('applied', 'stale_preserved') -- no PROCESSING, FAILED,
-- RETRYING, or CLAIMED states; DEFERRED is not stored at all, since a
-- deferred activation attempt makes no durable change to the occurrence.
ALTER TABLE artifact_occurrence
    ADD COLUMN activation_outcome text;

ALTER TABLE artifact_occurrence
    ADD CONSTRAINT artifact_occurrence_activation_outcome_known
    CHECK (activation_outcome IS NULL OR activation_outcome IN ('applied', 'stale_preserved'));

-- Resolved and unresolved are each all-or-nothing across both columns:
-- an occurrence can never durably carry a completion timestamp without
-- an outcome, or an outcome without a completion timestamp.
ALTER TABLE artifact_occurrence
    ADD CONSTRAINT artifact_occurrence_activation_resolution_consistent
    CHECK ((activation_completed_at IS NULL) = (activation_outcome IS NULL));
