"""SmartCart Ingestion TDD -- T3 (Stores half only): required chain
identity missing/empty must hard-fail; a present-but-unusual chain_id
(e.g. "0") must not be rejected merely for being unusual.

Test seam: transport.normalize -> parse.parse_stores_xml ->
validate.validate_stores -- the exact composed sequence run.py's
run_stores() calls, entered directly (no discovery/download/session
layer), matching tests/collectors/rami_levy/test_batch1_stores_regressions.py's
T1/T2/T9 tests (moved out of that file into this dedicated file so the T3
production change in src/smartcart/collectors/rami_levy/validate.py can be
committed together with exactly its own regression coverage, without
requiring the still-intentional T2/T9 RED to be part of the same commit).

Both fixtures in this file are PROVENANCE: SYNTHETIC_EVIDENCE_MOTIVATED_FIXTURE
-- neither reproduces bytes of, or is a copy/excerpt of, any physical
artifact; each is constructed from scratch, motivated by real market
evidence observed elsewhere in this engagement (see each fixture's own
comment block for which evidence and why).
"""

from __future__ import annotations

from smartcart.collectors.rami_levy import transport
from smartcart.collectors.rami_levy.parse import parse_stores_xml
from smartcart.collectors.rami_levy.validate import validate_stores

# ===========================================================================
# T3 (negative side) -- required chain identity missing/empty, store_id valid
# ===========================================================================
#
# PROVENANCE: SYNTHETIC_EVIDENCE_MOTIVATED_FIXTURE
# T-row: T3 (Stores half only -- PriceFull half explicitly out of scope
#   for this batch)
# This fixture is constructed entirely from scratch -- it is NOT
#   mechanically transformed from, and reproduces no bytes of, any
#   physical artifact. It is motivated by (not derived from) Super Cofix's
#   real evidence (ART2-0001), where chain_id and store_id were BOTH empty
#   together, which left open whether chain_id emptiness alone is
#   independently validated; this fixture isolates that one variable. It
#   uses the same general Rami-Levy-family Stores shape/casing/nesting
#   test_parse.py's own established VALID_STORES_XML fixture uses (uppercase
#   tag names, SubChains>SubChain>Stores>Store nesting), with the
#   <ChainID> tag entirely absent from the root while a fully valid,
#   non-empty <StoreID> is present -- never a real downloaded artifact, and
#   not a copy or excerpt of one.
# Critical distinction honored: the chain identity is MISSING (tag absent
#   entirely), not merely present-with-an-unusual-value such as "0" -- the
#   latter must not be, and is not, treated as missing here.
_CHAIN_ID_MISSING_STORES_XML_TEXT = (
    "<Root>"
    "<ChainName>Test Chain</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "<SubChains><SubChain>"
    "<SubChainID>001</SubChainID>"
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
CHAIN_ID_MISSING_STORES_XML = b"\xff\xfe" + _CHAIN_ID_MISSING_STORES_XML_TEXT.encode("utf-16-le")


def test_t3_stores_missing_chain_id_is_hard_fail() -> None:
    """EXPECTED_RED_REQUIREMENT_GAP (T3, Stores half only). Requirements:
    R1, R2, R6, R8, R9.

    EXACT EXPECTED RED: `assert outcome.hard_failed is True` fails, because
    current validate_stores() checks only store_id for emptiness/
    duplication and never inspects chain_id at all (confirmed by direct
    reading of validate.py) -- so a Stores record with a perfectly valid,
    non-empty store_id but an entirely-missing chain identity currently
    passes validation silently.

    If this fixture fails earlier, for a different reason (a parse
    exception, a malformed-fixture error), STOP -- do not adjust the
    fixture merely until the desired RED appears; that would indicate this
    predeclared gap does not exist as described and the RED Plan itself
    needs revisiting, not the fixture.
    """
    normalized = transport.normalize(CHAIN_ID_MISSING_STORES_XML)
    stores = parse_stores_xml(normalized)

    # Sanity: store_id parsed correctly and is non-empty -- this failure
    # must be attributable to chain_id alone, not to a broken fixture.
    assert len(stores) == 1
    assert stores[0].store_id == "039"
    assert stores[0].store_id != ""
    # Sanity: chain identity really is empty (missing tag -> "" via
    # parse.py's `_text(...) or ""`), not merely an unusual present value.
    assert stores[0].chain_id == ""

    outcome = validate_stores(stores)

    # THE EXPECTED RED.
    assert outcome.hard_failed is True, (
        "R6/R1 gap: validate_stores() does not reject a record with a "
        "missing chain_id as long as store_id is present and unique -- "
        f"got hard_failed=False, hard_fail_reasons={outcome.hard_fail_reasons!r} "
        f"for a record with chain_id={stores[0].chain_id!r}, "
        f"store_id={stores[0].store_id!r}."
    )


# ===========================================================================
# T3 (positive side) -- chain_id="0" is PRESENT, unusual, and must NOT be
# rejected merely for being unusual
# ===========================================================================
#
# PROVENANCE: SYNTHETIC_EVIDENCE_MOTIVATED_FIXTURE
# T-row: T3 (Stores half, positive regression)
# This fixture has NO physical-artifact source and is not a copy or excerpt
#   of any held artifact -- it is constructed from scratch. It is motivated
#   by real Keshet Taamim evidence (held in this engagement's corpus)
#   where <ChainId>0</ChainId> was physically observed, but this fixture
#   does not reuse Keshet's actual bytes/casing/shape; it uses the same
#   general Rami-Levy-family Stores shape test_parse.py's own
#   VALID_STORES_XML fixture and this file's own
#   CHAIN_ID_MISSING_STORES_XML fixture already use (uppercase tag names,
#   SubChains>SubChain>Stores>Store nesting), with <ChainID>0</ChainID>
#   PRESENT at the root (not absent, not empty) alongside a fully valid,
#   non-empty <StoreID>.
_CHAIN_ID_ZERO_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>0</ChainID>"
    "<ChainName>Test Chain</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "<SubChains><SubChain>"
    "<SubChainID>001</SubChainID>"
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
CHAIN_ID_ZERO_STORES_XML = b"\xff\xfe" + _CHAIN_ID_ZERO_STORES_XML_TEXT.encode("utf-16-le")


def test_t3_stores_chain_id_zero_is_present_and_not_rejected() -> None:
    """EXPECTED_GREEN_REGRESSION (T3, Stores half, positive side).
    Requirements: R1, R2, R6, R8, R9.

    Frozen semantic requirement being locked in: "0" is a PRESENT
    source-native chain_id value -- unusual, but not missing/empty -- and
    must not be rejected merely for being unusual. The assertion is
    intentionally narrow: it checks that no hard_fail_reason indicates an
    empty/invalid chain_id, not that the whole ValidationOutcome is
    failure-free (this fixture's other fields are not independently
    guaranteed exhaustive against every other unrelated validation rule).
    """
    normalized = transport.normalize(CHAIN_ID_ZERO_STORES_XML)
    stores = parse_stores_xml(normalized)

    # Sanity: chain_id is PRESENT ("0"), not empty -- distinct from the
    # missing-chain_id case above.
    assert len(stores) == 1
    assert stores[0].chain_id == "0"
    assert stores[0].store_id == "039"

    outcome = validate_stores(stores)

    # Narrow, semantic assertion: no hard-fail reason concerns an
    # empty/invalid chain_id. Deliberately not pinned to the exact
    # incidental wording used by the missing-chain_id case above.
    assert not any(
        "chain_id" in reason and "empty" in reason for reason in outcome.hard_fail_reasons
    ), (
        "T3 positive-side regression: chain_id='0' must be treated as a "
        "present, valid identity, never rejected merely for being unusual -- "
        f"got hard_fail_reasons={outcome.hard_fail_reasons!r}."
    )
