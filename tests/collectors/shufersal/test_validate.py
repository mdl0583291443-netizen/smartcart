"""Tests for smartcart.collectors.shufersal.validate.

All deterministic, no network access.
"""

from __future__ import annotations

from dataclasses import replace

from smartcart.collectors.shufersal.records import ShufersalPriceItemRaw, ShufersalStoreRaw
from smartcart.collectors.shufersal.validate import validate_pricefull, validate_stores

_BASE_STORE = ShufersalStoreRaw(
    chain_id="7290027600007",
    chain_name="Test Chain",
    subchain_id="1",
    subchain_name="Test Sub",
    store_id="1",
    bikoret_no="7",
    store_type="1",
    store_name="Test Store",
    address="Test Address",
    city="2530",
    zip_code="7030336",
)

_BASE_ITEM = ShufersalPriceItemRaw(
    chain_id="7290027600007",
    subchain_id="002",
    store_id="413",
    bikoret_no="0",
    price_update_time="2026-09-04T06:23:00",
    item_code="1",
    last_sale_date_time="2026-09-04T00:00:00",
    item_type="1",
    item_name="Test Item",
    manufacture_name="Acme",
    manufacture_country="IL",
    manufacture_item_description="Test Item",
    unit_qty="Gram",
    quantity="100.00",
    unit_of_measure="100 Gram",
    is_weighted="0",
    qty_in_package="1",
    item_price="10.00",
    unit_of_measure_price="10.00",
    allow_discount="1",
    item_status=None,
)


def _store(store_id: str) -> ShufersalStoreRaw:
    return replace(_BASE_STORE, store_id=store_id)


def _item(
    item_code: str,
    item_price: str = "10.00",
    *,
    chain_id: str = "7290027600007",
    subchain_id: str = "002",
    store_id: str = "413",
) -> ShufersalPriceItemRaw:
    return replace(
        _BASE_ITEM,
        item_code=item_code,
        item_price=item_price,
        unit_of_measure_price=item_price,
        chain_id=chain_id,
        subchain_id=subchain_id,
        store_id=store_id,
    )


def _pricefull_filename(chain_id: str, subchain_id: str, store_id: str) -> str:
    return f"PriceFull{chain_id}-{subchain_id}-{store_id}-20260907-034000.gz"


def _matching_filename(item: ShufersalPriceItemRaw) -> str:
    return _pricefull_filename(item.chain_id, item.subchain_id, item.store_id)


# --- Stores ---------------------------------------------------------------


def test_validate_stores_valid_passes() -> None:
    outcome = validate_stores([_store("1"), _store("2")])
    assert not outcome.hard_failed
    assert outcome.warnings == []


def test_validate_stores_zero_records_is_hard_fail() -> None:
    outcome = validate_stores([])
    assert outcome.hard_failed
    assert any("0 Store records" in reason for reason in outcome.hard_fail_reasons)


def test_validate_stores_empty_store_id_is_hard_fail() -> None:
    outcome = validate_stores([_store("")])
    assert outcome.hard_failed


def test_validate_stores_duplicate_store_id_is_hard_fail() -> None:
    outcome = validate_stores([_store("1"), _store("1")])
    assert outcome.hard_failed
    assert any("Duplicate store_id" in reason for reason in outcome.hard_fail_reasons)


# --- PriceFull --------------------------------------------------------------


def test_validate_pricefull_matching_ids_passes() -> None:
    item = _item("1")
    outcome = validate_pricefull([item], source_filename=_matching_filename(item))
    assert not outcome.hard_failed
    assert outcome.ids_matched is True


def test_validate_pricefull_mismatched_ids_is_hard_fail() -> None:
    item = _item("1", store_id="413")
    wrong_filename = _pricefull_filename(item.chain_id, item.subchain_id, "999")
    outcome = validate_pricefull([item], source_filename=wrong_filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


def test_validate_pricefull_unparseable_filename_is_hard_fail() -> None:
    item = _item("1")
    outcome = validate_pricefull([item], source_filename="not-a-recognized-filename.gz")
    assert outcome.hard_failed


def test_validate_pricefull_zero_records_is_hard_fail() -> None:
    outcome = validate_pricefull(
        [], source_filename=_pricefull_filename("7290027600007", "002", "413")
    )
    assert outcome.hard_failed
    assert any("0 Item records" in reason for reason in outcome.hard_fail_reasons)


def test_validate_pricefull_duplicate_item_code_is_warning_not_hard_fail() -> None:
    item_a = _item("1")
    item_b = _item("1")
    outcome = validate_pricefull([item_a, item_b], source_filename=_matching_filename(item_a))
    assert not outcome.hard_failed
    assert any("duplicate ItemCode" in warning for warning in outcome.warnings)


def test_validate_pricefull_valid_decimal_price_passes() -> None:
    item = _item("1", item_price="46.50")
    outcome = validate_pricefull([item], source_filename=_matching_filename(item))
    assert not outcome.hard_failed


def test_validate_pricefull_invalid_price_is_hard_fail() -> None:
    item = _item("1", item_price="not-a-price")
    outcome = validate_pricefull([item], source_filename=_matching_filename(item))
    assert outcome.hard_failed


def test_validate_pricefull_missing_price_is_hard_fail() -> None:
    item = replace(_item("1"), item_price=None)
    outcome = validate_pricefull([item], source_filename=_matching_filename(item))
    assert outcome.hard_failed


def test_validate_pricefull_zero_and_negative_price_do_not_crash_and_are_warnings() -> None:
    item_zero = _item("1", item_price="0.00")
    item_negative = _item("2", item_price="-5.00")
    outcome = validate_pricefull(
        [item_zero, item_negative], source_filename=_matching_filename(item_zero)
    )
    assert not outcome.hard_failed
    assert any("zero or negative" in warning.lower() for warning in outcome.warnings)


def test_validate_pricefull_low_positive_record_count_is_not_hard_fail_and_no_warning() -> None:
    """A single record is a valid, non-zero record count. Phase 1A has no
    historical baseline to judge "low" against, so no arbitrary threshold
    warning is raised -- only 0 records is a failure (see FIX 1)."""
    item = _item("1")
    outcome = validate_pricefull([item], source_filename=_matching_filename(item))
    assert not outcome.hard_failed
    assert outcome.warnings == []
