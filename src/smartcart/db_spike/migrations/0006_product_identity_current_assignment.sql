-- 0006_product_identity_current_assignment: Product Identity Slice-A
-- Batch-B foundation.
--
-- The current, authoritative assignment of a Retailer Tracking Identity
-- (chain_id, item_code_raw) to a SmartCart Product (product_id). Holds
-- ONLY the current assignment -- no timestamps, no history, no
-- valid_from/valid_to, no confidence/candidate/resolver fields, no
-- source-name fields (those are future/deferred concerns, not touched
-- here). No assignment row for a given Tracking Identity means
-- UNRESOLVED. product_id is deliberately NOT UNIQUE: cross-retailer
-- many->one assignment is allowed (multiple Tracking Identities, from
-- different chains, may reference the same Product); same-retailer
-- many->one remains UNKNOWN and is neither asserted nor enforced by this
-- schema.

CREATE TABLE chain_product_current_assignment (
    chain_id text NOT NULL,
    item_code_raw text NOT NULL,
    product_id bigint NOT NULL,
    PRIMARY KEY (chain_id, item_code_raw),
    FOREIGN KEY (chain_id, item_code_raw) REFERENCES chain_product (chain_id, item_code_raw),
    FOREIGN KEY (product_id) REFERENCES smartcart_product (product_id)
);
