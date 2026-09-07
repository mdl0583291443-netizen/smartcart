"""Semantic validation of parsed Rami Levy Stores/PriceFull data.

Runs after parse.py has already succeeded -- a malformed-XML or
unrecognized-schema failure is a parse-stage failure, not a
validation-stage one, and is never raised from here. Returns a structured
ValidationOutcome rather than raising, so callers can distinguish "hard
fail" from "succeeded with warnings" without exception-based control flow.

Deliberately does NOT warn or fail on:
- quantity == 0
- a field containing the literal "לא ידוע" placeholder, or any other
  nonnumeric quantity-like source value
- item_price <= 0 (no such value has been observed in either PriceFull
  schema family; if live acceptance ever does, that is a new finding to
  report and review, not a rule to quietly add here)
- any positive record count, however low (no historical baseline exists
  yet to judge "low" against; see docs/adr/0004 and the equivalent
  decision already made for Shufersal)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from smartcart.collectors.rami_levy.parse import schema_family_of
from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
    RamiLevyStoreRaw,
)

# Mirrors discovery.py's two known real PriceFull filename shapes so the
# ID cross-check can extract whatever tokens a given filename actually
# carries (the compact/online shape has no subchain segment). This is
# filename-shape parsing only -- it has no bearing on which XML schema
# family the file actually contains (see parse.py for that).
_PRICEFULL_STANDARD_RE = re.compile(
    r"^pricefull(?P<chain_id>\d+)-(?P<subchain_id>\d+)-(?P<store_id>\d+)-\d{8}-\d{6}\.gz$",
    re.IGNORECASE,
)
_PRICEFULL_COMPACT_RE = re.compile(
    r"^pricefull(?P<chain_id>\d+)-(?P<store_id>\d+)-\d{12}\.gz$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationOutcome:
    """Structured result of validating one parsed Rami Levy file."""

    hard_fail_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    filename_ids: dict[str, str | None] = field(default_factory=dict)
    xml_ids: dict[str, str | None] = field(default_factory=dict)
    ids_matched: bool | None = None

    @property
    def hard_failed(self) -> bool:
        return bool(self.hard_fail_reasons)


def parse_pricefull_filename_ids(filename: str) -> dict[str, str] | None:
    """Extract whatever chain/subchain/store IDs a PriceFull filename
    carries. Returns None if it matches neither known shape. The compact
    (online-store) shape has no subchain segment, so its result omits
    "subchain_id" entirely rather than guessing a value for it.
    """
    match = _PRICEFULL_STANDARD_RE.match(filename)
    if match is not None:
        return {
            "chain_id": match.group("chain_id"),
            "subchain_id": match.group("subchain_id"),
            "store_id": match.group("store_id"),
        }
    match = _PRICEFULL_COMPACT_RE.match(filename)
    if match is not None:
        return {"chain_id": match.group("chain_id"), "store_id": match.group("store_id")}
    return None


def _ids_match(key: str, filename_value: str, xml_value: str | None, *, schema_family: str) -> bool:
    """Compare one filename-derived ID token against its XML-derived
    counterpart for one file.

    Exact string equality in every case, EXCEPT: for the "online"
    PriceFull schema family specifically, the "store_id" token is compared
    numerically (e.g. "039" == "39"). This is the one evidence-backed,
    family-scoped equivalence agreed for that source's own observed
    padding discrepancy (catalog/filename "039" vs. XML-carried "39") --
    it is not a general ID normalizer: it never applies to "chain_id" or
    "subchain_id", never applies to the standard family, never mutates
    either value, and fails (returns False) both for a genuine numeric
    mismatch and for any non-numeric value on either side.
    """
    if schema_family == "online" and key == "store_id":
        if xml_value is None or not filename_value.isdigit() or not xml_value.isdigit():
            return False
        return int(filename_value) == int(xml_value)
    return filename_value == xml_value


def _parse_decimal(raw_value: str | None) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        return Decimal(raw_value)
    except InvalidOperation:
        return None


def validate_stores(stores: list[RamiLevyStoreRaw]) -> ValidationOutcome:
    """Validate parsed Rami Levy Stores records.

    Hard fails on: zero records, any empty store_id, or duplicate
    store_id values. Warns (does not hard fail) if any store_id's
    digit-length deviates from the most common width observed in the
    file -- reconnaissance observed all sampled StoreIDs zero-padded to
    3 digits, but there is no published spec guaranteeing a fixed width.
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

    numeric_ids = [store.store_id for store in stores if store.store_id.strip().isdigit()]
    if numeric_ids:
        lengths = Counter(len(store_id) for store_id in numeric_ids)
        common_length, _ = lengths.most_common(1)[0]
        deviating = sorted({sid for sid in numeric_ids if len(sid) != common_length})
        if deviating:
            warnings.append(
                f"{len(deviating)} store_id value(s) have a different digit-length than "
                f"this file's most common width ({common_length}): {deviating[:5]}."
            )

    return ValidationOutcome(hard_fail_reasons=hard_fail_reasons, warnings=warnings)


def validate_pricefull(
    items: list[RamiLevyPriceItemRawStandard] | list[RamiLevyPriceItemRawOnline],
    *,
    source_filename: str,
) -> ValidationOutcome:
    """Validate parsed Rami Levy PriceFull records, for either schema
    family (see parse.schema_family_of()).

    Hard fails on: zero records, filename-derived IDs disagreeing with
    XML-derived IDs (only for whichever ID fields the filename actually
    carries, and using the family-scoped equivalence rule for the online
    family's store_id -- see _ids_match), or any item_price that is not
    decimal-shaped.

    Warns (does not hard fail) on: duplicate item_code.
    """
    hard_fail_reasons: list[str] = []
    warnings: list[str] = []

    if not items:
        hard_fail_reasons.append("0 Item records found in PriceFull file.")
        return ValidationOutcome(hard_fail_reasons=hard_fail_reasons, warnings=warnings)

    schema_family = schema_family_of(items) or "standard"
    first = items[0]
    xml_ids: dict[str, str | None] = {
        "chain_id": first.chain_id,
        "subchain_id": first.subchain_id,
        "store_id": first.store_id,
    }
    filename_ids = parse_pricefull_filename_ids(source_filename)

    if filename_ids is None:
        hard_fail_reasons.append(
            f"Could not parse chain/store IDs from PriceFull filename {source_filename!r} "
            "using either known filename shape."
        )
        ids_matched = None
    else:
        mismatched = {
            k: (v, xml_ids.get(k))
            for k, v in filename_ids.items()
            if not _ids_match(k, v, xml_ids.get(k), schema_family=schema_family)
        }
        ids_matched = not mismatched
        if mismatched:
            hard_fail_reasons.append(
                f"Filename-derived IDs disagree with XML-derived IDs: {mismatched} "
                f"(filename_ids={filename_ids}, xml_ids={xml_ids}, "
                f"schema_family={schema_family!r})."
            )

    price_decimals = [(item.item_code, _parse_decimal(item.item_price)) for item in items]
    invalid_price_codes = [code for code, price in price_decimals if price is None]
    if invalid_price_codes:
        hard_fail_reasons.append(
            f"{len(invalid_price_codes)} item(s) have a non-decimal-shaped ItemPrice, "
            f"e.g. {invalid_price_codes[:5]}."
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
