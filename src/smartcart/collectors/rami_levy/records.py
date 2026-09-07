"""Plain data containers for the Rami Levy Phase 1A collector.

These are plain @dataclass definitions with no inheritance and no behavior
beyond simple derived properties -- deliberately not sharing a base class
with Shufersal's equivalent records yet (see docs/adr/0004). `RamiLevyStoreRaw`
preserves the Rami Levy Stores source representation exactly as observed in
reconnaissance (numeric-looking values stay strings, missing elements stay
None, "לא ידוע" is preserved verbatim as a real string value rather than
translated to None). `FileOutcome` and `RunSummary` carry operational
metadata only and never embed payload.

Targeted live-variant reconnaissance (see docs/adr/0007) found PriceFull is
published under two structurally distinct source schemas. Rather than
merge them into one synthetic model, each gets its own source-faithful raw
dataclass -- `RamiLevyPriceItemRawStandard` and `RamiLevyPriceItemRawOnline`
-- with no inheritance relationship between them. A function receiving
PriceFull items works with `list[RamiLevyPriceItemRawStandard] |
list[RamiLevyPriceItemRawOnline]` (a plain type union, not a merged model)
and determines which one it has via `parse.schema_family_of()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RamiLevyStoreRaw:
    """One <Store> record from a Rami Levy Stores file, source-faithful.

    Field set matches what reconnaissance observed under each <Store>
    element (StoreID, BikoretNo, StoreType, StoreName, Address, City,
    ZipCode -- note the source tag is "ZipCode", not Shufersal's
    "ZIPCode"), plus the ChainID/ChainName/SubChainID/SubChainName each
    store was nested under so grouping information is not lost when
    stores are returned as a flat list.
    """

    chain_id: str
    chain_name: str | None
    subchain_id: str
    subchain_name: str | None
    store_id: str
    bikoret_no: str | None
    store_type: str | None
    store_name: str | None
    address: str | None
    city: str | None
    zip_code: str | None


@dataclass(frozen=True)
class RamiLevyPriceItemRawStandard:
    """One <Item> record from a "standard"-schema Rami Levy PriceFull file,
    source-faithful. This is the family observed for 98 of 99 stores.

    Field set matches the same 17-tag Item schema observed for Shufersal
    (PriceUpdateTime .. ItemStatus) plus the file-level
    ChainID/SubChainID/StoreID/BikoretNo each item's file was published
    under. Numeric-looking values are kept as strings -- no coercion to
    int/float/Decimal happens here, and the literal placeholder string
    "לא ידוע" ("unknown") observed in several fields (notably
    QtyInPackage, which was "לא ידוע" in 100% of the sampled file) is
    preserved verbatim, not translated to None.
    """

    chain_id: str
    subchain_id: str
    store_id: str
    bikoret_no: str | None

    price_update_time: str | None
    item_code: str
    last_sale_date_time: str | None
    item_type: str | None
    item_name: str | None
    manufacture_name: str | None
    manufacture_country: str | None
    manufacture_item_description: str | None
    unit_qty: str | None
    quantity: str | None
    unit_of_measure: str | None
    is_weighted: str | None
    qty_in_package: str | None
    item_price: str | None
    unit_of_measure_price: str | None
    allow_discount: str | None
    item_status: str | None


@dataclass(frozen=True)
class RamiLevyPriceItemRawOnline:
    """One <Item> record from the "online"-schema Rami Levy PriceFull file,
    source-faithful. To date this family has been observed only for the
    single StoreType=2 (online) store, StoreID 039.

    This is a genuinely different 16-tag source schema, not a variant of
    the standard one: field names differ (PriceUpdateDate not
    PriceUpdateTime, ItemNm not ItemName, ManufacturerName not
    ManufactureName, ManufacturerItemDescription not
    ManufactureItemDescription -- note ManufactureCountry keeps its
    standard spelling, the rename is not a uniform prefix change), and
    LastSaleDateTime does not exist in this family at all -- there is no
    field to hold `None` for it here, since a field with no source
    equivalent should not exist rather than always be empty.

    The XML-carried StoreId in this family was observed as "39" (unpadded)
    while the corresponding filename/catalog token is "039" -- both
    representations are preserved exactly as-is here; only validate.py's
    family-scoped identity check treats them as equivalent, and never by
    mutating either value (see validate.py).
    """

    chain_id: str
    subchain_id: str
    store_id: str
    bikoret_no: str | None

    price_update_date: str | None
    item_code: str
    item_type: str | None
    item_nm: str | None
    manufacturer_name: str | None
    manufacture_country: str | None
    manufacturer_item_description: str | None
    unit_qty: str | None
    quantity: str | None
    unit_of_measure: str | None
    is_weighted: str | None
    qty_in_package: str | None
    item_price: str | None
    unit_of_measure_price: str | None
    allow_discount: str | None
    item_status: str | None


@dataclass(frozen=True)
class FileOutcome:
    """Operational metadata/outcome for processing exactly one source file.

    Carries no payload (no store/item objects) -- only sizes, counts, IDs,
    timing, and validation results. Deliberately shaped differently from
    Shufersal's FileOutcome where the two chains' realities differ (e.g.
    there is no signed-URL-expiry concept for Rami Levy) rather than
    forcing a shared base class.
    """

    file_kind: str  # "stores" or "pricefull"
    source_filename: str | None
    store_id: str | None  # requested store_id for pricefull; None for stores

    discovered_at: datetime | None
    download_completed_at: datetime | None
    # Named generically (not "compressed"/"decompressed") because transport
    # is content-aware here: Stores is never actually compressed, so
    # "compressed_bytes" would misstate what happened. downloaded_bytes is
    # the size as received over the wire; normalized_bytes is the size
    # after transport.normalize() (unchanged if the input wasn't gzip).
    downloaded_bytes: int | None
    normalized_bytes: int | None

    record_count: int | None

    # "standard" | "online" | None -- for PriceFull, which of the two known
    # source schemas parse.py detected (see parse.schema_family_of()).
    # Always None for Stores and for any outcome that never reached a
    # successful parse. This is an observational field only; it is never
    # used to drive discovery/transport/validation decisions.
    schema_family: str | None = None

    filename_ids: dict[str, str | None] = field(default_factory=dict)
    xml_ids: dict[str, str | None] = field(default_factory=dict)
    ids_matched: bool | None = None

    succeeded: bool = False
    hard_fail_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # "discovery" | "download" | "transport" | "parse" | "validation" | None
    failed_stage: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    stage_durations_seconds: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSummary:
    """Summary of one Phase 1A run: one FileOutcome per processed file.

    Also carries session-level operational metadata (login/re-login), since
    unlike Shufersal, Rami Levy requires an authenticated session that can
    expire mid-run. Deliberately holds no parsed payload and no raw file
    bodies, regardless of outcome.
    """

    started_at: datetime
    finished_at: datetime
    session_established: bool
    relogin_count: int = 0
    outcomes: list[FileOutcome] = field(default_factory=list)
    run_level_failure_reason: str | None = None

    @property
    def succeeded_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.succeeded)

    @property
    def failed_count(self) -> int:
        return sum(1 for outcome in self.outcomes if not outcome.succeeded)
