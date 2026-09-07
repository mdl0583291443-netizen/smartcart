"""Tests for smartcart.collectors.rami_levy.validate.

All deterministic, no network access.
"""

from __future__ import annotations

from dataclasses import replace

from smartcart.collectors.rami_levy.records import (
    RamiLevyPriceItemRawOnline,
    RamiLevyPriceItemRawStandard,
    RamiLevyStoreRaw,
)
from smartcart.collectors.rami_levy.validate import validate_pricefull, validate_stores

_BASE_STORE = RamiLevyStoreRaw(
    chain_id="7290058140886",
    chain_name="רמי לוי שיווק השקמה",
    subchain_id="001",
    subchain_name="1",
    store_id="001",
    bikoret_no="6",
    store_type="1",
    store_name="תלפיות",
    address="האומן,15",
    city="3000",
    zip_code="9342110",
)

_BASE_STANDARD_ITEM = RamiLevyPriceItemRawStandard(
    chain_id="7290058140886",
    subchain_id="001",
    store_id="731",
    bikoret_no="0",
    price_update_time="2026-04-27T11:19:43.000",
    item_code="7290000139159",
    last_sale_date_time="2026-08-19T16:40:12.000",
    item_type="1",
    item_name="Test Item",
    manufacture_name="לא ידוע",
    manufacture_country="לא ידוע",
    manufacture_item_description="Test Item",
    unit_qty="גרם",
    quantity="100.00",
    unit_of_measure="100 גרם",
    is_weighted="0",
    qty_in_package="לא ידוע",
    item_price="10.20",
    unit_of_measure_price="3.68",
    allow_discount="1",
    item_status=None,
)

_BASE_ONLINE_ITEM = RamiLevyPriceItemRawOnline(
    chain_id="7290058140886",
    subchain_id="1",
    store_id="39",
    bikoret_no="3",
    price_update_date="2025-01-19 16:03:55",
    item_code="6",
    item_type="1",
    item_nm="Test Item",
    manufacturer_name="לא ידוע",
    manufacture_country="לא ידוע",
    manufacturer_item_description="Test Item",
    unit_qty="יחידים",
    quantity="1",
    unit_of_measure="1 יחידים",
    is_weighted="0",
    qty_in_package="6.0000",
    item_price="30.6",
    unit_of_measure_price="30.6",
    allow_discount="1",
    item_status="1",
)


def _store(store_id: str) -> RamiLevyStoreRaw:
    return replace(_BASE_STORE, store_id=store_id)


def _item(
    item_code: str, item_price: str = "10.20", *, store_id: str = "731"
) -> RamiLevyPriceItemRawStandard:
    return replace(
        _BASE_STANDARD_ITEM, item_code=item_code, item_price=item_price, store_id=store_id
    )


def _online_item(
    item_code: str = "6", item_price: str = "30.6", *, store_id: str = "39"
) -> RamiLevyPriceItemRawOnline:
    return replace(_BASE_ONLINE_ITEM, item_code=item_code, item_price=item_price, store_id=store_id)


def _standard_filename(chain_id: str, subchain_id: str, store_id: str) -> str:
    return f"PriceFull{chain_id}-{subchain_id}-{store_id}-20260907-113823.gz"


def _compact_filename(chain_id: str, store_id: str) -> str:
    return f"pricefull{chain_id}-{store_id}-202609070518.gz"


def _matching_standard_filename(item: RamiLevyPriceItemRawStandard) -> str:
    return _standard_filename(item.chain_id, item.subchain_id, item.store_id)


# --- Stores ---------------------------------------------------------------


def test_validate_stores_valid_passes() -> None:
    outcome = validate_stores([_store("001"), _store("002")])
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
    outcome = validate_stores([_store("001"), _store("001")])
    assert outcome.hard_failed
    assert any("Duplicate store_id" in reason for reason in outcome.hard_fail_reasons)


def test_validate_stores_zero_padding_deviation_is_warning_not_hard_fail() -> None:
    outcome = validate_stores([_store("001"), _store("002"), _store("003"), _store("4")])
    assert not outcome.hard_failed
    assert any("digit-length" in warning for warning in outcome.warnings)


# --- PriceFull: standard family identity -----------------------------------


def test_validate_pricefull_standard_matching_ids_passes() -> None:
    item = _item("1")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert not outcome.hard_failed
    assert outcome.ids_matched is True


def test_validate_pricefull_standard_mismatched_store_id_is_hard_fail() -> None:
    item = _item("1", store_id="731")
    wrong_filename = _standard_filename(item.chain_id, item.subchain_id, "999")
    outcome = validate_pricefull([item], source_filename=wrong_filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


def test_validate_pricefull_unrecognized_filename_shape_is_hard_fail() -> None:
    item = _item("1")
    outcome = validate_pricefull([item], source_filename="not-a-recognized-filename.gz")
    assert outcome.hard_failed


def test_validate_pricefull_zero_records_is_hard_fail() -> None:
    outcome = validate_pricefull(
        [], source_filename=_standard_filename("7290058140886", "001", "731")
    )
    assert outcome.hard_failed
    assert any("0 Item records" in reason for reason in outcome.hard_fail_reasons)


# --- PriceFull: online family identity (039/"39" equivalence) --------------


def test_validate_pricefull_online_zero_padded_filename_vs_unpadded_xml_passes() -> None:
    """The one evidence-backed, family-scoped equivalence: filename token
    "039" vs. XML-carried "39" is accepted for validation purposes only,
    for the online family's store_id specifically."""
    item = _online_item(store_id="39")
    filename = _compact_filename(item.chain_id, "039")
    outcome = validate_pricefull([item], source_filename=filename)
    assert not outcome.hard_failed
    assert outcome.ids_matched is True
    # Neither representation was mutated to match the other.
    assert item.store_id == "39"
    assert outcome.filename_ids["store_id"] == "039"
    assert outcome.xml_ids["store_id"] == "39"
    # The compact filename shape carries no subchain token at all.
    assert "subchain_id" not in outcome.filename_ids


def test_validate_pricefull_online_genuine_numeric_mismatch_is_hard_fail() -> None:
    """A real difference (not just padding) must still fail -- the
    equivalence rule is not a blanket "ignore store_id" allowance."""
    item = _online_item(store_id="40")
    filename = _compact_filename(item.chain_id, "039")
    outcome = validate_pricefull([item], source_filename=filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


def test_validate_pricefull_online_nonnumeric_xml_store_id_fails_honestly() -> None:
    """A non-numeric XML store_id must not crash the comparison -- it is
    simply treated as a mismatch (hard fail), same as any other identity
    disagreement."""
    item = _online_item(store_id="ABC")
    filename = _compact_filename(item.chain_id, "039")
    outcome = validate_pricefull([item], source_filename=filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


def test_validate_pricefull_standard_family_does_not_get_numeric_equivalence() -> None:
    """The same padding-tolerant comparison must NOT apply to the standard
    family -- an exact string mismatch there is a hard fail even if the
    two values are numerically equal."""
    item = _item("1", store_id="039")
    filename = _standard_filename(item.chain_id, item.subchain_id, "39")
    outcome = validate_pricefull([item], source_filename=filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


def test_validate_pricefull_online_chain_id_still_requires_exact_match() -> None:
    """The numeric-equivalence allowance is scoped to store_id only -- a
    chain_id mismatch in the online family must still hard fail even if
    the values happen to be numerically different by a small amount."""
    item = replace(_online_item(store_id="39"), chain_id="7290058140887")
    filename = _compact_filename("7290058140886", "039")
    outcome = validate_pricefull([item], source_filename=filename)
    assert outcome.hard_failed
    assert outcome.ids_matched is False


# --- PriceFull: price/duplicates (applies to both families identically) ----


def test_validate_pricefull_valid_decimal_price_passes() -> None:
    item = _item("1", item_price="10.20")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert not outcome.hard_failed


def test_validate_pricefull_invalid_price_is_hard_fail() -> None:
    item = _item("1", item_price="not-a-price")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert outcome.hard_failed


def test_validate_pricefull_missing_price_is_hard_fail() -> None:
    item = replace(_item("1"), item_price=None)
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert outcome.hard_failed


def test_validate_pricefull_duplicate_item_code_is_warning_not_hard_fail() -> None:
    item_a = _item("1")
    item_b = _item("1")
    outcome = validate_pricefull(
        [item_a, item_b], source_filename=_matching_standard_filename(item_a)
    )
    assert not outcome.hard_failed
    assert any("duplicate ItemCode" in warning for warning in outcome.warnings)


def test_validate_pricefull_online_invalid_price_is_hard_fail() -> None:
    item = _online_item(item_price="not-a-price")
    filename = _compact_filename(item.chain_id, "039")
    outcome = validate_pricefull([item], source_filename=filename)
    assert outcome.hard_failed


# --- No validation event for these observed-normal conditions --------------


def test_validate_pricefull_zero_quantity_field_triggers_no_validation_event() -> None:
    """Quantity is not inspected by validation at all -- zero quantity is
    a real, valid observed value, not a warning or failure condition."""
    item = replace(_item("1"), quantity="0.00")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert not outcome.hard_failed
    assert outcome.warnings == []


def test_validate_pricefull_la_yadua_descriptive_fields_trigger_no_validation_event() -> None:
    """The base fixture already has manufacture_name/manufacture_country/
    qty_in_package set to the literal 'לא ידוע' placeholder -- this must
    not produce any warning or hard failure."""
    item = _item("1")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert not outcome.hard_failed
    assert outcome.warnings == []


def test_validate_pricefull_low_positive_record_count_has_no_threshold_warning() -> None:
    """No historical baseline exists yet -- any positive record count,
    however low, must not trigger a warning (see docs/adr/0004)."""
    item = _item("1")
    outcome = validate_pricefull([item], source_filename=_matching_standard_filename(item))
    assert not outcome.hard_failed
    assert outcome.warnings == []
