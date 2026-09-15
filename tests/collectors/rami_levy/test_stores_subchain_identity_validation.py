"""SmartCart Ingestion TDD -- T4 (Stores half only): required subchain
identity -- missing, empty, or whitespace-only -- must hard-fail; a
present-but-unusual subchain_id (e.g. the observed zero-padded "000") must
not be rejected merely for being unusual.

Frozen requirement (T4): for the currently supported Stores validation
seam (transport.normalize -> parse.parse_stores_xml -> validate_stores),
subchain_id is REQUIRED BY PRESENCE ONLY -- missing/empty/whitespace-only
must hard-fail specifically on subchain_id; any other non-empty value is
opaque and must never be format-validated.

Evidence basis for this frozen requirement (T4 recon, this engagement):

OBSERVED FACT: a physical-evidence census of 57 real acquired Price/
PriceFull/Stores/StoresFull artifacts across 21 entities and 3 acquisition
waves found subchain_id (SubChainID/SubChainId) present and non-empty in
every single case -- no missing, empty, or whitespace-only physical
occurrence was found anywhere in that corpus.

OBSERVED FACT: several real entities (City_Market_Shops, City_Market_
KiryatGat, Good_Pharm, King_Store, Shefa_Birkat_Hashem, Wolt) physically
carry a zero-padded "000" subchain_id in their Price/PriceFull/Stores
files -- a present, unusual, but entirely legitimate observed value.

DECISION: T4 nevertheless freezes a presence-only requirement for the
supported Stores validation seam. Absence of a missing/empty physical
counterexample is not proof such a source can never exist, and
validate_stores() currently performs no check of any kind on subchain_id
(confirmed by direct reading of validate.py this engagement) -- an
already-parsed empty subchain_id can pass through validation completely
silently today. T4 closes exactly that gap, narrowly: presence only, no
format/casing opinion.

Not claimed by T4 (explicitly out of scope):
- "0" (bare, unpadded) was never physically observed for subchain_id in
  this corpus -- only the zero-padded "000" form was; this file's T4-D
  positive control uses "000" for that reason, not "0".
- That every retailer/schema must carry a SubChainID tag, or that this
  requirement generalizes beyond the currently supported Stores schema.
- That any non-XML source family must have an equivalent concept.
- That Super Cofix's parser behavior is correct (see note below).
- That this fixes SubChainId casing/family-detection in any way.

Super Cofix follow-up note (separate, not addressed here): Super Cofix's
real Stores.xml physically carries <SubChainId>1</SubChainId> (non-empty),
but the current Stores parser (_extract_store_records(), hardcoded to the
uppercase-only "SubChainID" tag name with no family branching) silently
loses that value to "" for that entity's real bytes -- a parser casing
defect, not a validation-presence question. That defect is a separate,
not-yet-authorized follow-up slice. T4 only ensures that an
ALREADY-PARSED empty subchain_id (however it came to be empty -- by a
genuinely missing/empty/whitespace source tag, OR by an unrelated parser
defect like Super Cofix's) cannot pass validate_stores() silently. This
file's own fixtures do not use Super Cofix or any other physical artifact,
and do not exercise or fix that parser defect.

Test seam: transport.normalize -> parse.parse_stores_xml ->
validate.validate_stores -- the exact composed sequence run.py's
run_stores() calls, entered directly, matching this engagement's existing
T3 file (test_stores_chain_identity_validation.py) and its own T1/T2/T9
predecessor.

All fixtures in this file are PROVENANCE: SYNTHETIC_EVIDENCE_MOTIVATED_
FIXTURE -- none reproduces bytes of, or is a copy/excerpt of, any physical
artifact (Super Cofix explicitly excluded, per instruction, to avoid
confounding this validation-only claim with that entity's separate,
already-documented parser casing defect). Each uses the same general
Rami-Levy-family Stores shape/casing/nesting as test_parse.py's own
VALID_STORES_XML and this engagement's T3 fixtures (uppercase tag names,
SubChains>SubChain>Stores>Store nesting), with a fully valid, non-empty,
non-duplicate chain_id and store_id held constant across all four cases so
that any observed hard-fail (or its absence) is attributable to
subchain_id alone, never to chain_id/store_id.
"""

from __future__ import annotations

from smartcart.collectors.rami_levy import transport
from smartcart.collectors.rami_levy.parse import parse_stores_xml
from smartcart.collectors.rami_levy.validate import validate_stores


def _stores_xml(subchain_id_tag: str) -> bytes:
    """Build one Stores document with a valid, constant chain_id/store_id
    and exactly the given raw <SubChainID>...</SubChainID> (or absent)
    markup substituted in -- so only subchain_id varies across T4's four
    cases below."""
    text = (
        "<Root>"
        "<ChainID>7290058140886</ChainID>"
        "<ChainName>Test Chain</ChainName>"
        "<LastUpdateDate>2026-09-07</LastUpdateDate>"
        "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
        "<SubChains><SubChain>"
        f"{subchain_id_tag}"
        "<SubChainName>1</SubChainName>"
        "<Stores><Store>"
        "<StoreID>039</StoreID>"
        "<BikoretNo>9</BikoretNo>"
        "<StoreType>2</StoreType>"
        "<StoreName>Test Store</StoreName>"
        "<Address>Test Address</Address>"
        "<City>3000</City>"
        "<ZipCode>9342110</ZipCode>"
        "</Store></Stores>"
        "</SubChain></SubChains></Root>"
    )
    return b"\xff\xfe" + text.encode("utf-16-le")


# ===========================================================================
# T4-A -- subchain identity MISSING (no <SubChainID> tag at all)
# ===========================================================================

MISSING_SUBCHAIN_ID_STORES_XML = _stores_xml("")


def test_t4a_stores_missing_subchain_id_is_hard_fail() -> None:
    """EXPECTED_RED_REQUIREMENT_GAP (T4-A). Requirement: T4 (see module
    docstring).

    EXACT EXPECTED RED: an assertion that this hard-fails specifically on
    subchain_id fails, because validate_stores() currently performs no
    check of subchain_id at all (confirmed by direct reading of
    validate.py) -- a Stores record with a perfectly valid, non-empty,
    non-duplicate chain_id/store_id but an entirely-missing subchain
    identity currently passes validation silently.

    If this fixture fails earlier, for a different reason (a parse
    exception, a malformed-fixture error, or a chain_id/store_id failure),
    classify as UNEXPECTED_RED and stop -- do not adjust the fixture.
    """
    normalized = transport.normalize(MISSING_SUBCHAIN_ID_STORES_XML)
    stores = parse_stores_xml(normalized)

    # Sanity: exactly one store, chain_id/store_id both valid and
    # non-empty -- any failure below must be attributable to subchain_id
    # alone, never to chain_id or store_id.
    assert len(stores) == 1
    assert stores[0].chain_id == "7290058140886"
    assert stores[0].store_id == "039"
    # Sanity: subchain identity really is empty (missing tag -> "" via
    # parse.py's `_text(...) or ""`), not merely an unusual present value.
    assert stores[0].subchain_id == ""

    outcome = validate_stores(stores)

    # THE EXPECTED RED.
    assert any("subchain_id" in reason for reason in outcome.hard_fail_reasons), (
        "T4 gap: validate_stores() does not reject a record with a "
        "missing subchain_id as long as chain_id/store_id are present and "
        f"valid -- got hard_failed={outcome.hard_failed}, "
        f"hard_fail_reasons={outcome.hard_fail_reasons!r} for a record with "
        f"subchain_id={stores[0].subchain_id!r}."
    )


# ===========================================================================
# T4-B -- subchain identity EMPTY (<SubChainID></SubChainID>)
# ===========================================================================

EMPTY_SUBCHAIN_ID_STORES_XML = _stores_xml("<SubChainID></SubChainID>")


def test_t4b_stores_empty_subchain_id_is_hard_fail() -> None:
    """EXPECTED_RED_REQUIREMENT_GAP (T4-B). Requirement: T4 (see module
    docstring). Same expected gap as T4-A, for a present-but-empty tag
    rather than an absent one."""
    normalized = transport.normalize(EMPTY_SUBCHAIN_ID_STORES_XML)
    stores = parse_stores_xml(normalized)

    assert len(stores) == 1
    assert stores[0].chain_id == "7290058140886"
    assert stores[0].store_id == "039"
    assert stores[0].subchain_id == ""

    outcome = validate_stores(stores)

    assert any("subchain_id" in reason for reason in outcome.hard_fail_reasons), (
        "T4 gap: validate_stores() does not reject a record with an "
        "empty subchain_id as long as chain_id/store_id are present and "
        f"valid -- got hard_failed={outcome.hard_failed}, "
        f"hard_fail_reasons={outcome.hard_fail_reasons!r} for a record with "
        f"subchain_id={stores[0].subchain_id!r}."
    )


# ===========================================================================
# T4-C -- subchain identity WHITESPACE-ONLY (<SubChainID>   </SubChainID>)
# ===========================================================================

WHITESPACE_SUBCHAIN_ID_STORES_XML = _stores_xml("<SubChainID>   </SubChainID>")


def test_t4c_stores_whitespace_only_subchain_id_is_hard_fail() -> None:
    """EXPECTED_RED_REQUIREMENT_GAP (T4-C). Requirement: T4 (see module
    docstring). Same expected gap as T4-A/T4-B, for a tag present with
    whitespace-only text -- distinct from empty, since parse.py's `_text`
    treats a non-empty (even whitespace-only) string as present and does
    NOT coerce it to ''."""
    normalized = transport.normalize(WHITESPACE_SUBCHAIN_ID_STORES_XML)
    stores = parse_stores_xml(normalized)

    assert len(stores) == 1
    assert stores[0].chain_id == "7290058140886"
    assert stores[0].store_id == "039"
    # Sanity: genuinely whitespace-only, not coerced to "" by parse.py, and
    # not accidentally empty (which would make this indistinguishable from
    # T4-B).
    assert stores[0].subchain_id != ""
    assert stores[0].subchain_id.strip() == ""

    outcome = validate_stores(stores)

    assert any("subchain_id" in reason for reason in outcome.hard_fail_reasons), (
        "T4 gap: validate_stores() does not reject a record with a "
        "whitespace-only subchain_id as long as chain_id/store_id are "
        f"present and valid -- got hard_failed={outcome.hard_failed}, "
        f"hard_fail_reasons={outcome.hard_fail_reasons!r} for a record with "
        f"subchain_id={stores[0].subchain_id!r}."
    )


# ===========================================================================
# T4-D -- observed positive control: subchain_id="000" must NOT be rejected
# ===========================================================================

ZERO_PADDED_SUBCHAIN_ID_STORES_XML = _stores_xml("<SubChainID>000</SubChainID>")


def test_t4d_stores_zero_padded_subchain_id_is_present_and_not_rejected() -> None:
    """EXPECTED_GREEN_REGRESSION (T4-D). Requirement: T4 (see module
    docstring).

    Frozen semantic requirement being locked in: a zero-padded "000" is a
    PRESENT, source-native, physically-observed subchain_id value (see
    module docstring's OBSERVED FACT) -- unusual, but not missing/empty --
    and must not be rejected merely for being unusual. The assertion is
    intentionally narrow: it checks that no hard-fail reason concerns
    subchain_id, not that the whole ValidationOutcome is failure-free --
    this fixture's other fields are not independently guaranteed
    exhaustive against every other unrelated validation rule.
    """
    normalized = transport.normalize(ZERO_PADDED_SUBCHAIN_ID_STORES_XML)
    stores = parse_stores_xml(normalized)

    # Sanity: subchain_id is PRESENT ("000"), not empty -- distinct from
    # T4-A/T4-B/T4-C above.
    assert len(stores) == 1
    assert stores[0].chain_id == "7290058140886"
    assert stores[0].store_id == "039"
    assert stores[0].subchain_id == "000"

    outcome = validate_stores(stores)

    # Narrow, semantic assertion: no hard-fail reason concerns subchain_id
    # at all -- deliberately not asserting outcome.hard_failed is False,
    # since this fixture's other fields are not independently guaranteed
    # exhaustive against every other unrelated validation rule.
    assert not any("subchain_id" in reason for reason in outcome.hard_fail_reasons), (
        "T4 positive-side regression: subchain_id='000' must be treated as "
        "a present, valid identity, never rejected merely for being "
        f"unusual -- got hard_fail_reasons={outcome.hard_fail_reasons!r}."
    )
