# 0007. Rami Levy PriceFull: two distinct source schema families

## Status

Accepted

## Context

Targeted live reconnaissance classified all 321 PriceFull entries in the
current Rami Levy listing (98 stores' worth). It found two structurally
distinct source families, not one format with minor variation:

- **Standard** (266 listing entries, 98 stores): filename
  `PriceFull<chain>-<subchain>-<store>-<date8>-<time6>.gz`, gzip
  container, root tags `ChainID`/`SubChainID`/`StoreID`, a 17-tag Item
  schema (`PriceUpdateTime` .. `ItemStatus`), `StoreID` zero-padded and
  matching the filename token exactly.
- **Online** (55 listing entries, exactly StoreID 039 -- the chain's sole
  `StoreType=2` store): filename
  `pricefull<chain>-<store>-<timestamp12>.gz`, but a **ZIP** archive
  despite the `.gz` name, containing one XML member with root tags
  `ChainId`/`SubChainId`/`StoreId` and a different 16-tag Item schema
  (`PriceUpdateDate` not `PriceUpdateTime`, `ItemNm` not `ItemName`,
  `ManufacturerName`/`ManufacturerItemDescription` not
  `ManufactureName`/`ManufactureItemDescription`, and no
  `LastSaleDateTime` field at all). Its `StoreId` value is `"39"`
  (unpadded), while the filename/catalog token is `"039"`.

No third family was found; all 321 entries fit one of these two shapes.

## Decision

Both families are supported as first-class, independently-defined source
representations:

- **Two raw dataclasses, not one merged model**: `RamiLevyPriceItemRawStandard`
  (17 fields) and `RamiLevyPriceItemRawOnline` (16 fields, its own field
  names, no `last_sale_date_time` field at all -- not an always-`None`
  one). Merging them into a single dataclass with optional/aliased fields
  would misrepresent both: it would imply a field exists in a schema that
  never carries it, and would hide that these are two different upstream
  data-generation pipelines, not one schema with occasional gaps.
- **Content/schema-based family detection, not StoreID-based**: `parse.py`
  determines which family an XML document belongs to strictly from its
  own root-tag casing (`ChainID` vs. `ChainId`), never from the store_id
  that was requested or the filename shape that led to discovery. A
  document matching neither known root-tag pattern is an explicit parse
  failure (`ParseError`), never a guess or a partial/fuzzy field mapping.
  This means the design does not silently break if a *different* store
  someday publishes under the online schema, or if 039 someday switches
  to the standard one -- the content decides, every time.
- **Transport is content-aware for containers too**: `transport.py`
  detects gzip vs. ZIP vs. plain-passthrough purely from magic bytes,
  with an in-memory-only, single-member, size-bounded ZIP extraction path
  (see the module for the exact safety contract and the 100 MB ceiling,
  which is a resource-exhaustion guard, not a data-quality signal).
- **The 039 `"039"`/`"39"` equivalence is validation-only and
  family-scoped**: `validate.py`'s identity cross-check treats the
  filename-derived `store_id` and the XML-derived `store_id` as
  equivalent under numeric comparison (`int("039") == int("39")`), but
  *only* for the online family's `store_id` field -- never for `chain_id`,
  never for the standard family, and never as a general-purpose ID
  normalizer elsewhere in the codebase. Both raw string representations
  (`"039"` and `"39"`) are preserved unchanged in the raw dataclasses and
  in `FileOutcome.filename_ids`/`xml_ids`; only the boolean
  match/mismatch decision applies the rule.
- **Raw source representations are never altered.** Renamed fields keep
  their own source-faithful names (`item_nm`, not a repurposed
  `item_name`); the literal Hebrew placeholder string is preserved exactly
  as stored (see the RTL/Unicode note below) with no reordering or
  translation anywhere in the pipeline.

## Consequences

- The current distribution (98 stores standard / 1 store online) is
  recorded here as an **observation from this reconnaissance pass**, not a
  permanent assumption baked into validation (no code asserts "exactly one
  online store" or "exactly 99 stores").
- A future, still-unrecognized third schema family fails closed: `parse.py`
  raises `ParseError` rather than attempting a best-effort mapping. That
  failure is scoped to the one file it occurred on (see the Phase 1A
  isolation design) and should prompt a repeat of this reconnaissance
  process, not a silent code change.
- This ADR intentionally does not generalize into a "source-variant
  framework" (a registry of schemas, a plugin mechanism, etc.) -- exactly
  two concrete, evidence-backed schemas are implemented, matching what has
  actually been observed live.
- A related, purely observational finding from the same reconnaissance
  pass: an earlier report displayed the placeholder string reversed
  ("עודי אל"); direct inspection of the raw UTF-8 bytes and Python
  code-point order confirmed this was a terminal/display (bidi rendering)
  artifact only -- the actual stored/logical value, in every fixture,
  test, and the parser itself, is and remains `"לא ידוע"`.
