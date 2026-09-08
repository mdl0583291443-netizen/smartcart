-- 0004_normalized_current_state_facts: Schema Slice 1 (docs/adr/0011).
--
-- Purely additive: adds the normalized source-fact columns and the
-- normalization-contract-version provenance column to
-- store_product_current_state. All six columns are nullable with no
-- default; no existing row is rewritten and no value is backfilled (see
-- ADR 0011 sections 2 and 3). No other table is touched.

ALTER TABLE store_product_current_state
    ADD COLUMN product_name text,
    ADD COLUMN declared_quantity numeric,
    ADD COLUMN declared_quantity_raw text,
    ADD COLUMN declared_quantity_unit_raw text,
    ADD COLUMN is_weighted boolean,
    ADD COLUMN normalization_contract_version integer,
    ADD CHECK (normalization_contract_version IS NULL OR normalization_contract_version >= 1);
