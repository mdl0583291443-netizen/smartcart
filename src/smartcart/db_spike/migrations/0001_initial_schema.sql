-- 0001_initial_schema: Focused DB Spike Round 1 minimum relational model.
--
-- Provisional (see docs/adr/0009-focused-db-spike.md): this schema exists
-- to test the fixed invariants of the Focused DB Spike, not to be a
-- finished production design. Only the fields/constraints required for
-- Round 1's tested invariants are present.

CREATE TABLE chain (
    chain_id text PRIMARY KEY,
    chain_name text
);

CREATE TABLE subchain (
    chain_id text NOT NULL REFERENCES chain (chain_id),
    subchain_id text NOT NULL,
    subchain_name text,
    PRIMARY KEY (chain_id, subchain_id)
);

-- Store has a SmartCart-owned, opaque surrogate identity (store_id). No
-- retailer raw store identifier is or influences this identity -- there
-- is deliberately no unique constraint here on any retailer-shaped value.
-- A bigserial surrogate is used (not a UUID): it is consistent with every
-- other surrogate key already in this schema (content_id, occurrence_id,
-- ingestion_run_id, price_history_id, store_source_alias_id), needs no
-- extension, and is smaller/faster to index than a UUID -- the lightest
-- sound option for this spike, not a production-scale bet (see
-- docs/adr/0009-focused-db-spike.md). chain_id/subchain_id remain because
-- they identify which chain/subchain the store belongs to, which is a
-- chain-level identity concern, not the retailer-store-identity concern
-- this correction addresses. UNIQUE (chain_id, store_id) exists solely so
-- dependent tables below can enforce, via a composite foreign key, that a
-- row's chain_id always matches its store's actual chain -- it is not a
-- second identity for Store.
CREATE TABLE store (
    store_id bigserial PRIMARY KEY,
    chain_id text NOT NULL,
    subchain_id text NOT NULL,
    store_name text,
    FOREIGN KEY (chain_id, subchain_id) REFERENCES subchain (chain_id, subchain_id),
    UNIQUE (chain_id, store_id)
);

-- Holds ALL retailer/source-specific raw store identifiers, preserved
-- exactly, for a SmartCart-owned Store. Neither raw_value here is ever
-- privileged as "the" canonical identifier -- Store.store_id (above) is
-- the only identity. This is exactly where the Rami Levy "039"
-- (filename/catalog token) vs. "39" (online-family XML-carried value)
-- both live, as two separate alias rows pointing at the same store_id
-- (see docs/adr/0007 for the source finding). chain_id is denormalized
-- from store.chain_id solely so the uniqueness constraint below can be
-- scoped per chain without a join.
CREATE TABLE store_source_alias (
    store_source_alias_id bigserial PRIMARY KEY,
    chain_id text NOT NULL,
    store_id bigint NOT NULL,
    source text NOT NULL,
    alias_context text NOT NULL,
    raw_value text NOT NULL,
    FOREIGN KEY (chain_id, store_id) REFERENCES store (chain_id, store_id),
    UNIQUE (chain_id, source, alias_context, raw_value)
);

-- Canonical immutable content identity/evidence. Identity is
-- SHA-256(exact decompressed/extracted source payload bytes), computed by
-- the caller (never derived from payload_bytes' storage encoding) over
-- the pre-parser, BOM-inclusive, unnormalized boundary established in the
-- Collector Contract Inspection. payload_bytes is this spike's ONE chosen
-- storage medium (see docs/adr/0009); content_hash/content_id identity
-- and every FK/relationship in this schema are defined independently of
-- how/where payload_bytes happens to be physically stored.
CREATE TABLE artifact_content (
    content_id bigserial PRIMARY KEY,
    content_hash text NOT NULL,
    payload_bytes bytea NOT NULL,
    payload_size_bytes bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT artifact_content_hash_format CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT artifact_content_size_matches_payload CHECK (payload_size_bytes = octet_length(payload_bytes)),
    UNIQUE (content_hash)
);

-- Envelope only, not a transaction boundary: one ingestion_run groups the
-- occurrences produced by one collector run for operational bookkeeping.
-- Occurrences are written independently, not inside one giant transaction
-- spanning the whole run (see docs/adr/0009 / Round 1 governance).
CREATE TABLE ingestion_run (
    ingestion_run_id bigserial PRIMARY KEY,
    source text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    CONSTRAINT ingestion_run_source_known CHECK (source IN ('shufersal', 'rami_levy'))
);

-- Fact/provenance of observing one ArtifactContent in one source context.
-- content_id is NOT NULL: an Occurrence can never exist without Content,
-- but Content may durably exist with zero Occurrences referencing it (see
-- Round 1 test 5). Validation outcome lives here, not on ArtifactContent,
-- because it is a fact about this observation, not an immutable property
-- of the payload bytes themselves (Fixed Data Invariant 2).
CREATE TABLE artifact_occurrence (
    occurrence_id bigserial PRIMARY KEY,
    content_id bigint NOT NULL REFERENCES artifact_content (content_id),
    ingestion_run_id bigint REFERENCES ingestion_run (ingestion_run_id),
    chain_id text NOT NULL,
    -- SmartCart-owned Store surrogate identity (see the store table
    -- above), never a retailer raw store identifier.
    store_id bigint,
    artifact_kind text NOT NULL,
    source_filename text,
    schema_family text,
    -- Per Fixed Data Invariant 4: captured immediately after successful
    -- artifact acquisition, timezone-aware UTC. Never discovery/listing
    -- time, source-updated time, or parse/validation completion time.
    collected_at timestamptz NOT NULL,
    validation_status text NOT NULL,
    validation_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT artifact_occurrence_kind_known CHECK (artifact_kind IN ('stores', 'pricefull')),
    CONSTRAINT artifact_occurrence_store_id_matches_kind CHECK (
        (artifact_kind = 'stores' AND store_id IS NULL)
        OR (artifact_kind = 'pricefull' AND store_id IS NOT NULL)
    ),
    CONSTRAINT artifact_occurrence_schema_family_known CHECK (
        schema_family IS NULL OR schema_family IN ('standard', 'online')
    ),
    CONSTRAINT artifact_occurrence_validation_status_known CHECK (
        validation_status IN ('valid', 'parse_failed', 'validation_failed')
    ),
    FOREIGN KEY (chain_id, store_id) REFERENCES store (chain_id, store_id)
);

CREATE INDEX artifact_occurrence_content_id_idx ON artifact_occurrence (content_id);
CREATE INDEX artifact_occurrence_store_collected_idx
    ON artifact_occurrence (chain_id, store_id, collected_at, occurrence_id);

-- Thin, chain-scoped product identity: the raw ItemCode string exactly as
-- the chain's own source represents it. No barcode-type inference, no
-- cross-chain matching (Fixed Data Invariant 9).
CREATE TABLE chain_product (
    chain_id text NOT NULL REFERENCES chain (chain_id),
    item_code_raw text NOT NULL,
    PRIMARY KEY (chain_id, item_code_raw)
);

-- Minimal shape only: Round 1 does not implement ordered/atomic
-- activation (that is Round 2). Rows here are written directly by test
-- helpers to prove the shape can hold and reference its originating
-- occurrence; no activation-ordering or idempotency enforcement exists
-- yet. current_price is the typed Decimal representation;
-- current_price_raw is the untouched raw source string -- one must never
-- destructively replace the other (Fixed Data Invariant 8).
CREATE TABLE store_product_current_state (
    chain_id text NOT NULL,
    -- SmartCart-owned Store surrogate identity, never a retailer raw
    -- store identifier.
    store_id bigint NOT NULL,
    item_code_raw text NOT NULL,
    current_price numeric NOT NULL,
    current_price_raw text NOT NULL,
    source_occurrence_id bigint NOT NULL REFERENCES artifact_occurrence (occurrence_id),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (chain_id, store_id, item_code_raw),
    FOREIGN KEY (chain_id, store_id) REFERENCES store (chain_id, store_id),
    FOREIGN KEY (chain_id, item_code_raw) REFERENCES chain_product (chain_id, item_code_raw)
);

-- Append-oriented price event history. No valid_to interval model (Fixed
-- Data Invariant 8): every observation, including the first, creates one
-- event row here; rows are never updated or superseded in place.
CREATE TABLE price_history (
    price_history_id bigserial PRIMARY KEY,
    chain_id text NOT NULL,
    -- SmartCart-owned Store surrogate identity, never a retailer raw
    -- store identifier.
    store_id bigint NOT NULL,
    item_code_raw text NOT NULL,
    price numeric NOT NULL,
    price_raw text NOT NULL,
    observed_at timestamptz NOT NULL,
    source_occurrence_id bigint NOT NULL REFERENCES artifact_occurrence (occurrence_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (chain_id, store_id) REFERENCES store (chain_id, store_id),
    FOREIGN KEY (chain_id, item_code_raw) REFERENCES chain_product (chain_id, item_code_raw)
);

CREATE INDEX price_history_lookup_idx
    ON price_history (chain_id, store_id, item_code_raw, observed_at);
