"""Plain data containers for the Shufersal Phase 1A collector.

These are plain @dataclass definitions with no inheritance and no behavior
beyond simple derived properties. `ShufersalStoreRaw` / `ShufersalPriceItemRaw`
preserve the Shufersal source representation as observed in reconnaissance
(numeric-looking values stay strings, missing elements stay None). `FileOutcome`
and `RunSummary` carry operational metadata only and never embed payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ShufersalStoreRaw:
    """One <Store> record from a Shufersal Stores file, source-faithful.

    Carries the ChainID/SubChainID/SubChainName each store was nested under
    in the source XML, so grouping information is not lost when stores are
    returned as a flat list. All fields are exactly as observed in the
    source: numeric-looking values (IDs, codes) are kept as strings, and
    missing/empty elements are kept as None rather than coerced to "" or 0.
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
class ShufersalPriceItemRaw:
    """One <Item> record from a Shufersal PriceFull file, source-faithful.

    Field set matches the stable 17-tag Item schema observed across all 10
    sampled Shufersal SubChainIDs during reconnaissance, plus the file-level
    ChainID/SubChainID/StoreID/BikoretNo each item's file was published
    under. Numeric-looking values (ItemCode, prices, quantities, flags) are
    kept as strings -- no coercion to int/float/Decimal happens here.
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
class FileOutcome:
    """Operational metadata/outcome for processing exactly one source file.

    Carries no payload (no store/item objects) -- only sizes, counts, IDs,
    timing, and validation results, so it stays small even when the
    underlying file has tens of thousands of records.
    """

    file_kind: str  # "stores" or "pricefull"
    source_filename: str | None
    store_id: str | None  # requested store_id for pricefull; None for stores

    discovered_at: datetime | None
    signed_url_expiry_raw: str | None

    download_completed_at: datetime | None
    compressed_bytes: int | None
    decompressed_bytes: int | None

    record_count: int | None

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

    Deliberately holds no parsed payload (no Raw store/item objects) so it
    stays small regardless of how many records the underlying files had.
    """

    started_at: datetime
    finished_at: datetime
    outcomes: list[FileOutcome] = field(default_factory=list)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.succeeded)

    @property
    def failed_count(self) -> int:
        return sum(1 for outcome in self.outcomes if not outcome.succeeded)
