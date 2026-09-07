"""Semantic validation of parsed Shufersal Stores/PriceFull data.

Runs after parse.py has already succeeded -- a malformed-XML failure is a
parse-stage failure, not a validation-stage one, and is never raised from
here. This module returns a structured ValidationOutcome rather than
raising, so callers can distinguish "hard fail" from "succeeded with
warnings" without exception-based control flow.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from smartcart.collectors.shufersal.records import ShufersalPriceItemRaw, ShufersalStoreRaw

_PRICEFULL_FILENAME_RE = re.compile(
    r"^PriceFull(?P<chain_id>\d+)-(?P<subchain_id>\d+)-(?P<store_id>\d+)-\d{8}-\d{6}\.gz$"
)


@dataclass(frozen=True)
class ValidationOutcome:
    """Structured result of validating one parsed Shufersal file."""

    hard_fail_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    filename_ids: dict[str, str | None] = field(default_factory=dict)
    xml_ids: dict[str, str | None] = field(default_factory=dict)
    ids_matched: bool | None = None

    @property
    def hard_failed(self) -> bool:
        return bool(self.hard_fail_reasons)


def parse_pricefull_filename_ids(filename: str) -> dict[str, str] | None:
    """Extract ChainID/SubChainID/StoreID from a PriceFull filename.

    Returns None if the filename does not match the observed
    `PriceFull<chain>-<subchain>-<store>-<date>-<time>.gz` pattern.
    """
    match = _PRICEFULL_FILENAME_RE.match(filename)
    if match is None:
        return None
    return {
        "chain_id": match.group("chain_id"),
        "subchain_id": match.group("subchain_id"),
        "store_id": match.group("store_id"),
    }


def _parse_decimal(raw_value: str | None) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None


def validate_stores(stores: list[ShufersalStoreRaw]) -> ValidationOutcome:
    """Validate parsed Shufersal Stores records.

    Hard fails on: zero records, any empty store_id, or duplicate
    store_id values.
    """
    hard_fail_reasons: list[str] = []
    warnings: list[str] = []

    if not stores:
        hard_fail_reasons.append("0 Store records found in Stores file.")
        return ValidationOutcome(hard_fail_reasons=hard_fail_reasons, warnings=warnings)

    empty_id_count = sum(1 for store in stores if not store.store_id.strip())
    if empty_id_count:
        hard_fail_reasons.append(f"{empty_id_count} Store record(s) have an empty store_id.")

    id_counts = Counter(store.store_id for store in stores if store.store_id.strip())
    duplicates = sorted(store_id for store_id, count in id_counts.items() if count > 1)
    if duplicates:
        hard_fail_reasons.append(f"Duplicate store_id value(s) found: {duplicates}.")

    return ValidationOutcome(hard_fail_reasons=hard_fail_reasons, warnings=warnings)


def validate_pricefull(
    items: list[ShufersalPriceItemRaw],
    *,
    source_filename: str,
) -> ValidationOutcome:
    """Validate parsed Shufersal PriceFull records.

    Hard fails on: zero records, filename-derived IDs disagreeing with
    XML-derived IDs, or any item_price that is not decimal-shaped.

    Warns (does not hard fail) on: duplicate item_code, or zero/negative
    item_price values -- these are recorded explicitly rather than assumed
    impossible.

    Any positive record count is accepted as-is (no "unexpectedly low"
    threshold): there is no historical baseline yet to judge "low" against
    (see docs/adr/0004), and inventing one would be a fabricated baseline.
    record_count is retained on FileOutcome for future comparison once a
    real baseline or explicit external expectation exists.
    """
    hard_fail_reasons: list[str] = []
    warnings: list[str] = []

    if not items:
        hard_fail_reasons.append("0 Item records found in PriceFull file.")
        return ValidationOutcome(hard_fail_reasons=hard_fail_reasons, warnings=warnings)

    # ID cross-check: filename-derived IDs are compared against the
    # XML-derived IDs carried on every item (all items in one PriceFull
    # file share the same file-level chain/subchain/store IDs).
    first = items[0]
    xml_ids: dict[str, str | None] = {
        "chain_id": first.chain_id,
        "subchain_id": first.subchain_id,
        "store_id": first.store_id,
    }
    filename_ids = parse_pricefull_filename_ids(source_filename)
    ids_matched = filename_ids is not None and dict(filename_ids) == xml_ids

    if filename_ids is None:
        hard_fail_reasons.append(
            f"Could not parse chain/subchain/store IDs from PriceFull filename {source_filename!r}."
        )
    elif not ids_matched:
        hard_fail_reasons.append(
            f"Filename-derived IDs {filename_ids} disagree with XML-derived IDs {xml_ids}."
        )

    price_decimals = [(item.item_code, _parse_decimal(item.item_price)) for item in items]

    invalid_price_codes = [code for code, price in price_decimals if price is None]
    if invalid_price_codes:
        hard_fail_reasons.append(
            f"{len(invalid_price_codes)} item(s) have a non-decimal-shaped ItemPrice, "
            f"e.g. {invalid_price_codes[:5]}."
        )

    zero_or_negative_codes = [
        code for code, price in price_decimals if price is not None and price <= 0
    ]
    if zero_or_negative_codes:
        warnings.append(
            f"{len(zero_or_negative_codes)} item(s) have a zero or negative ItemPrice, "
            f"e.g. {zero_or_negative_codes[:5]}."
        )

    code_counts = Counter(item.item_code for item in items)
    duplicate_codes = sorted(code for code, count in code_counts.items() if count > 1)
    if duplicate_codes:
        warnings.append(
            f"{len(duplicate_codes)} duplicate ItemCode value(s) found, e.g. {duplicate_codes[:5]}."
        )

    return ValidationOutcome(
        hard_fail_reasons=hard_fail_reasons,
        warnings=warnings,
        filename_ids=dict(filename_ids) if filename_ids is not None else {},
        xml_ids=xml_ids,
        ids_matched=ids_matched,
    )
