-- 0007_chain_product_assignment_history: Product Identity Slice-B
-- foundation.
--
-- Append-only history of superseded chain_product_current_assignment
-- rows (H1): when a Tracking Identity's assignment is corrected from
-- Product A to Product B, this table gains one row recording that A was
-- superseded -- it never models a two-sided correction event containing
-- both A and B. Rows are never updated or deleted. No reason/source/
-- actor/confidence/candidate fields, no valid_from/valid_to or
-- bitemporal modeling, and no Display Name or raw/source-name fields
-- live here -- those are explicitly deferred, not part of this Slice-B
-- foundation.

CREATE TABLE chain_product_assignment_history (
    assignment_history_id bigserial PRIMARY KEY,
    chain_id text NOT NULL,
    item_code_raw text NOT NULL,
    product_id bigint NOT NULL,
    superseded_at timestamptz NOT NULL,
    FOREIGN KEY (chain_id, item_code_raw) REFERENCES chain_product (chain_id, item_code_raw),
    FOREIGN KEY (product_id) REFERENCES smartcart_product (product_id)
);
