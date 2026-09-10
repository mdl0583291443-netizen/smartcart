-- 0005_product_identity_slice_a: Product Identity Slice-A Batch-A
-- foundation.
--
-- Minimal shape only (Batch A, per the approved Slice-A scope): a
-- SmartCart-owned Product identity, independent of any retailer
-- tracking identity. display_name is nullable and not unique -- a
-- Product may exist with no name, and naming is a separate concern
-- (Batch C) from creating the identity itself. No retailer/tracking
-- key, no GTIN, no source-name preservation, no assignment/link table,
-- and no history live here -- those are Batch B/C and Slice B.

CREATE TABLE smartcart_product (
    product_id bigserial PRIMARY KEY,
    display_name text
);
