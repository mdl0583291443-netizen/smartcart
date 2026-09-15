-- 0008_normalized_occurrence_evidence: T13 Slice A minimum shape.
--
-- Durable, immutable normalized-item evidence for one already-durable,
-- store-scoped ArtifactOccurrence, captured BEFORE projection activation
-- (see src/smartcart/db_spike/normalized_evidence.py's module docstring
-- for the full T13 pipeline/frozen-semantics context). This migration
-- covers only what T13 RED-1/RED-13 require; later slices (RED-2..RED-5)
-- may extend this table additively (e.g. a provenance/version column) --
-- nothing here should be read as foreclosing that.
--
-- store_id here is the RESOLVED SmartCart-owned internal store surrogate
-- (see the store table), never a raw retailer store identifier -- there
-- is deliberately no raw-store-token column: that identity is already
-- preserved separately, durably, in store_source_alias.
--
-- item_sequence_index is the ONLY semantic ordering signal: it records
-- the position each item held in its originally-supplied sequence.
-- evidence_id is a plain operational surrogate primary key and must never
-- be treated as, or substituted for, semantic ordering.
--
-- Deliberately NOT added yet (later RED tests, not this migration):
-- UNIQUE(occurrence_id, item_sequence_index), UNIQUE(occurrence_id,
-- item_code_raw) (item_code_raw uniqueness within one occurrence is not
-- evidence-backed -- see this engagement's T13 recon), any provenance/
-- contract-version column, any activation-outcome/rebuild-generation/
-- active-projection marker.
CREATE TABLE normalized_occurrence_evidence (
    evidence_id bigserial PRIMARY KEY,
    occurrence_id bigint NOT NULL REFERENCES artifact_occurrence (occurrence_id),
    item_sequence_index integer NOT NULL,
    chain_id text NOT NULL,
    -- SmartCart-owned Store surrogate identity (resolved), never a
    -- retailer raw store identifier.
    store_id bigint NOT NULL,
    item_code_raw text NOT NULL,
    price numeric NOT NULL,
    price_raw text NOT NULL,
    collected_at timestamptz NOT NULL,
    product_name text NOT NULL,
    declared_quantity numeric NOT NULL,
    declared_quantity_raw text NOT NULL,
    declared_quantity_unit_raw text NOT NULL,
    is_weighted boolean,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (chain_id, store_id) REFERENCES store (chain_id, store_id)
);

CREATE INDEX normalized_occurrence_evidence_occurrence_sequence_idx
    ON normalized_occurrence_evidence (occurrence_id, item_sequence_index);
