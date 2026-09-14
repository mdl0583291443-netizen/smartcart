"""SmartCart Ingestion TDD -- Tests First, Batch 1: T1.

T3 (Stores half only: chain identity missing/empty, store_id valid) has
been moved out of this file into its own dedicated file,
tests/collectors/rami_levy/test_stores_chain_identity_validation.py.

T2/T9's original inequality diagnostic
(test_t2_t9_true_empty_source_is_operationally_indistinguishable_from_h_cohen)
has been REMOVED from this file: it was an intentionally-RED diagnostic
proving the R2 observability gap existed, and that gap is now closed.
Permanent semantic coverage for T2/T9 lives in
tests/collectors/rami_levy/test_stores_structural_observability.py, which
asserts the real distinction directly (RECOGNIZED_EMPTY vs.
NONEMPTY_UNRECOGNIZED, plus RECOGNIZED_NONEMPTY and UNKNOWN_UNCLASSIFIED)
rather than merely asserting the two outcomes differ.

Test seam for T1: transport.normalize -> parse.parse_stores_xml ->
validate.validate_stores -- the exact composed sequence run.py's
run_stores() calls, entered directly (no discovery/download/session
layer).

Frozen RED Plan classification (Phase 0, prior session):

- T1 (Super Cofix, real lowercase-d Stores artifact): EXPECTED_GREEN_REGRESSION

No production code is modified or exercised outside its existing public
functions. See the fixture's own comment block for its exact provenance
classification (PHYSICAL_ARTIFACT_VERBATIM_EXCERPT).
"""

from __future__ import annotations

from smartcart.collectors.rami_levy import transport
from smartcart.collectors.rami_levy.parse import parse_stores_xml
from smartcart.collectors.rami_levy.validate import validate_stores

# ===========================================================================
# T1 -- SUPER COFIX (real artifact)
# ===========================================================================
#
# PROVENANCE: PHYSICAL_ARTIFACT_VERBATIM_EXCERPT
# T-row: T1
# Entity/source: Super Cofix (Rami Levy BaShchuna), Wave 2
# Physical artifact ID: ART2-0001
# Original source path (held evidence, NOT modified):
#   ~/smartcart-data/source-diversity/wave2/artifacts/Super_Cofix/
#   Stores7291056200008-202609120510.xml
# Container/encoding, verified by direct inspection of the held artifact:
#   RAW (uncompressed), UTF-8 with BOM, root/child tag casing
#   ChainId/SubChainId/StoreId (lowercase-d) throughout -- NOT the
#   ChainID/SubChainID/StoreID casing parse_stores_xml() hardcodes. Since
#   the original container is RAW (no compression), this fixture's bytes
#   ARE the same representation as the held artifact for the portion
#   included below -- this is NOT true for the gzip/ZIP fixtures elsewhere
#   in this file/batch, whose original compressed container bytes are not
#   reproduced (see their own provenance notes).
# NOT a complete copy of the physical artifact: the real file holds 34
# <Store> elements; this fixture embeds only the header and the FIRST 3 of
# those 34 <Store> elements. Every byte that IS included (tag names,
# casing, the real Hebrew store names/addresses/cities) is copied
# unchanged, verbatim, from the held artifact -- nothing within the
# included excerpt is invented or altered. The remaining 31 stores are
# TRUNCATED, omitted only for fixture size/readability; this fixture must
# not be read as reproducing the artifact's full record count or full byte
# content. Included content is directory/store-locator data (name,
# address, city), not competitively-sensitive pricing data. The UTF-8 BOM
# prefix (b"\xef\xbb\xbf") is prepended explicitly in code rather than
# carried as a literal BOM character in the Python string literal.
_SUPER_COFIX_REAL_EXCERPT = (
    '<Root><ChainId>7291056200008</ChainId><ChainName>רמי לוי בשכונה</ChainName>'
    '<XmlDocVersion>00000</XmlDocVersion><LastUpdateDate>2026-09-12</LastUpdateDate>'
    '<LastUpdateTime>05:10:00</LastUpdateTime><SubChains><SubChain>'
    '<SubChainId>1</SubChainId><SubChainName>1</SubChainName><Stores>'
    '<Store><StoreId>299</StoreId><BikoretNo>9</BikoretNo><StoreType>1</StoreType>'
    '<StoreName>רמילוי בשכונה פרדסיה</StoreName><Address>הארז 33</Address>'
    '<City>פרדסיה</City><ZipCode>unknown</ZipCode></Store>'
    '<Store><StoreId>302</StoreId><BikoretNo>2</BikoretNo><StoreType>1</StoreType>'
    '<StoreName>ר.בשכונה שטמפפר פ"ת</StoreName><Address>שטמפפר 37</Address>'
    '<City>פתח תקווה</City><ZipCode>unknown</ZipCode></Store>'
    '<Store><StoreId>306</StoreId><BikoretNo>8</BikoretNo><StoreType>1</StoreType>'
    '<StoreName>ר.בשכונה חדרה הרצל</StoreName><Address>הרצל 27</Address>'
    '<City>חדרה</City><ZipCode>unknown</ZipCode></Store>'
    '</Stores></SubChain></SubChains></Root>'
)
SUPER_COFIX_REAL_STORES_XML = b"\xef\xbb\xbf" + _SUPER_COFIX_REAL_EXCERPT.encode("utf-8")


def test_t1_super_cofix_real_artifact_composed_seam_is_loud_not_silent() -> None:
    """EXPECTED_GREEN_REGRESSION (T1). Requirements: R1, R2, R3, R6.

    This test does NOT stop at parse-only output as its final assertion
    (the bare parser result is asserted only as an intermediate fact, to
    document what the Engine Compatibility Audit originally observed). The
    final, load-bearing assertions are against the COMPOSED
    transport->parse->validate seam, exactly as run_stores() calls it.

    This must NOT be read as proving a silent end-to-end failure -- the
    opposite is what this test proves: the real artifact's identity
    corruption is caught, loudly, by validate_stores(), before it could
    ever reach persistence.
    """
    normalized = transport.normalize(SUPER_COFIX_REAL_STORES_XML)

    stores = parse_stores_xml(normalized)
    # Intermediate fact only (matches the Engine Compatibility Audit's
    # direct-execution finding): the bare parser silently produces rows
    # with empty identity for this real, lowercase-d artifact.
    assert len(stores) == 3
    assert all(store.chain_id == "" for store in stores)
    assert all(store.store_id == "" for store in stores)

    # Final, composed-seam assertions -- this is the actual claim under test.
    outcome = validate_stores(stores)
    assert outcome.hard_failed is True
    assert any("empty store_id" in reason for reason in outcome.hard_fail_reasons)

# T2/T9's old inequality diagnostic (H. Cohen vs. a genuinely-empty Stores
# document) was intentionally removed from here once superseded -- see this
# file's module docstring for where its permanent replacement lives.
