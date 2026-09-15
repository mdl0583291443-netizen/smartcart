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

--- T1 CONTRACT MIGRATION (this session) -------------------------------

OLD T1 CONTRACT (superseded, not silently discarded -- recorded here for
history): the then-known parser corruption (Super Cofix's real lowercase-d
identity tags being silently read as empty by the uppercase-only Stores
parser) had to fail LOUDLY at validate_stores() rather than pass silently
with corrupted identity. That was itself already a positive requirement,
proven against the actually-shipped defective parser of that time.

NEW T1 CONTRACT (this session, once a lowercase-d/uppercase-D alias
requirement was frozen for Stores identity extraction): the physically
observed lowercase-d Super Cofix identity (chain_id, subchain_id, and each
store's store_id) must be PRESERVED, correctly and non-empty, by the
composed Stores seam -- not merely caught-and-rejected after being lost.

This is a CONTRACT UPGRADE, not a weakening: the positive regression this
test provides continues to protect against silent identity loss end to
end: it previously did so by requiring a loud hard-fail (the only safe
outcome achievable against the then-current, uppercase-only parser); it
now does so by requiring correct preservation (the only outcome now
frozen as correct, once the parser supports the observed casing
aliases). Both versions share the same underlying purpose -- Super
Cofix's real identity must never reach persistence silently corrupted --
expressed against two different points in the parser's own evolution.

As of this session, the required parser change (ChainID/ChainId,
SubChainID/SubChainId, StoreID/StoreId aliasing for Stores identity
extraction) has NOT yet been implemented -- this migrated test is
EXPECTED TO FAIL (RED) against the current parser, exactly mirroring the
same TDD discipline already used for T4/T5 elsewhere in this engagement:
the test is written first, against the frozen requirement, before the
implementation exists.

Test renamed accordingly: the old name
(test_t1_super_cofix_real_artifact_composed_seam_is_loud_not_silent)
described the OLD contract's required outcome (loud failure) and would
now be actively misleading, since the frozen future-correct outcome is
successful parsing/validation, not failure. The new name
(test_t1_super_cofix_composed_seam_preserves_lowercase_identity)
describes the permanent contract this test now protects.

Frozen RED Plan classification (Phase 0, prior session; T1's own
classification is superseded by the contract migration above -- this
particular test is now, as of this session, an intentional EXPECTED_RED
pending the not-yet-implemented Stores identity-casing-alias parser
change):

- T1 (Super Cofix, real lowercase-d Stores artifact): see migration note
  above -- no longer EXPECTED_GREEN_REGRESSION as originally classified.

No production code is modified or exercised outside its existing public
functions. See the fixture's own comment block for its exact provenance
classification (PHYSICAL_PAYLOAD_DERIVED_EXCERPT_UTF16LE -- corrected this
session from the prior, factually inaccurate
PHYSICAL_ARTIFACT_VERBATIM_EXCERPT/"UTF-8 with BOM" claim; see the
fixture's own comment block for exactly what was and was not verified).
"""

from __future__ import annotations

from smartcart.collectors.rami_levy import transport
from smartcart.collectors.rami_levy.parse import parse_stores_xml
from smartcart.collectors.rami_levy.validate import validate_stores

# ===========================================================================
# T1 -- SUPER COFIX (derived excerpt, physically-observed identity values)
# ===========================================================================
#
# PROVENANCE: PHYSICAL_PAYLOAD_DERIVED_EXCERPT_UTF16LE
# T-row: T1
# Entity/source: Super Cofix (Rami Levy BaShchuna), Wave 2
# Physical artifact ID: ART2-0001
# Original source path (held evidence, NOT modified):
#   ~/smartcart-data/source-diversity/wave2/artifacts/Super_Cofix/
#   Stores7291056200008-202609120510.xml
#
# CORRECTION (this session): the prior version of this fixture's provenance
#   note claimed "RAW (uncompressed), UTF-8 with BOM" and labelled itself
#   PHYSICAL_ARTIFACT_VERBATIM_EXCERPT. Direct byte-level inspection this
#   session found that claim factually WRONG: the real file's first four
#   bytes are `ff fe 3c 00` -- UTF-16LE with a UTF-16 BOM, not UTF-8. That
#   inaccurate claim does not survive into this version.
#
# OBSERVED PHYSICAL FACT (re-verified this session, direct byte-level
#   inspection of the real file, not inferred from any prior report):
#   - Container: RAW (uncompressed).
#   - Encoding: UTF-16LE with BOM (first 4 bytes `ff fe 3c 00`).
#   - Root/child tag casing: ChainId/SubChainId/StoreId (lowercase-d)
#     throughout, with ZERO occurrences anywhere in the document of
#     ChainID/SubChainID/StoreID (uppercase-D) -- fully, consistently
#     lowercase-cased at every structural level (root, subchain, all 34
#     stores).
#   - <ChainId>7291056200008</ChainId> (root, one occurrence).
#   - <SubChainId>1</SubChainId> (the one <SubChain> element).
#   - 34 total <Store> elements, each carrying its own <StoreId>; the
#     first three, in document order, are "299", "302", "306".
#
# DERIVED TEST FIXTURE (what this fixture actually is):
#   - A reconstructed, self-contained XML document, NOT a byte-for-byte
#     excerpt verified against the real file's byte range -- no exact
#     byte-equality check was performed for any portion of it, so it is
#     NOT called verbatim, byte-faithful, or a raw physical artifact.
#   - It reuses the real, physically-observed identity values above
#     (ChainId, SubChainId, and the first 3 StoreId values) and the real
#     Hebrew store name/address/city text for those same 3 stores,
#     independently re-verified this session by decoding the real file
#     directly (not copied from the prior fixture or any prior report).
#   - Encoded as UTF-16LE with a UTF-16 BOM (b"\xff\xfe" + ...encode
#     ("utf-16-le")), matching the real artifact's OBSERVED ENCODING
#     FAMILY, so that transport.normalize() exercises the same real
#     encoding class this entity's Stores files actually use.
#   - Only the first 3 of the real file's 34 <Store> elements are
#     included; the remaining 31 are omitted for fixture size, exactly as
#     the prior version of this fixture also did.
_SUPER_COFIX_DERIVED_EXCERPT = (
    "<Root><ChainId>7291056200008</ChainId><ChainName>רמי לוי בשכונה</ChainName>"
    "<XmlDocVersion>00000</XmlDocVersion><LastUpdateDate>2026-09-12</LastUpdateDate>"
    "<LastUpdateTime>05:10:00</LastUpdateTime><SubChains><SubChain>"
    "<SubChainId>1</SubChainId><SubChainName>1</SubChainName><Stores>"
    "<Store><StoreId>299</StoreId><BikoretNo>9</BikoretNo><StoreType>1</StoreType>"
    "<StoreName>רמילוי בשכונה פרדסיה</StoreName><Address>הארז 33</Address>"
    "<City>פרדסיה</City><ZipCode>unknown</ZipCode></Store>"
    "<Store><StoreId>302</StoreId><BikoretNo>2</BikoretNo><StoreType>1</StoreType>"
    "<StoreName>ר.בשכונה שטמפפר פ\"ת</StoreName><Address>שטמפפר 37</Address>"
    "<City>פתח תקווה</City><ZipCode>unknown</ZipCode></Store>"
    "<Store><StoreId>306</StoreId><BikoretNo>8</BikoretNo><StoreType>1</StoreType>"
    "<StoreName>ר.בשכונה חדרה הרצל</StoreName><Address>הרצל 27</Address>"
    "<City>חדרה</City><ZipCode>unknown</ZipCode></Store>"
    "</Stores></SubChain></SubChains></Root>"
)
SUPER_COFIX_DERIVED_STORES_XML = b"\xff\xfe" + _SUPER_COFIX_DERIVED_EXCERPT.encode("utf-16-le")


def test_t1_super_cofix_composed_seam_preserves_lowercase_identity() -> None:
    """EXPECTED_SEMANTIC_RED (T1, migrated). Requirements: R1, R2, R3, R6.

    NEW, permanent T1 contract (see module docstring's migration note):
    the composed Stores seam must PRESERVE Super Cofix's real,
    lowercase-d source-native identity (chain_id, subchain_id, each
    store's store_id) -- not merely fail loudly once it is already lost.

    EXACT EXPECTED RED: against the current parser (which reads only the
    uppercase-D ChainID/SubChainID/StoreID tags -- confirmed by direct
    reading of parse.py's _extract_store_records() this session), the
    first identity-preservation assertion below (chain_id) fails, because
    the real lowercase-d value is still silently read as "". This
    identical class of loss also affects subchain_id and every store_id
    in this fixture -- if this specific first assertion is fixed without
    the others, the RED will simply move to the next one, which is the
    expected/correct behavior of this test, not a sign to adjust it.

    If this fails for any OTHER reason -- a transport/decoding exception,
    an unexpected store count, a non-identity field (e.g. store_name)
    being wrong, or an unrelated validate_stores() failure -- that is an
    UNEXPECTED_RED: stop, do not adjust the fixture, and do not touch
    production to force this test green.
    """
    normalized = transport.normalize(SUPER_COFIX_DERIVED_STORES_XML)
    stores = parse_stores_xml(normalized)

    # Sanity: transport/decoding and structural parsing both succeeded,
    # and reached the intended semantic layer -- a non-identity field
    # (store_name, which parse.py extracts via a casing-invariant tag
    # name) is correct, proving this is not an encoding/decoding/parse
    # failure in disguise.
    assert len(stores) == 3
    assert stores[0].store_name == "רמילוי בשכונה פרדסיה"

    # THE EXPECTED RED (identity preservation, not mere loud rejection).
    assert all(store.chain_id == "7291056200008" for store in stores), (
        "T1 (migrated): chain_id must preserve the real, lowercase-d "
        "<ChainId> value -- the current uppercase-only parser still "
        f"silently loses it. Got: {[s.chain_id for s in stores]!r}."
    )
    assert all(store.subchain_id == "1" for store in stores), (
        "T1 (migrated): subchain_id must preserve the real, lowercase-d "
        "<SubChainId> value -- the current uppercase-only parser still "
        f"silently loses it. Got: {[s.subchain_id for s in stores]!r}."
    )
    assert [store.store_id for store in stores] == ["299", "302", "306"], (
        "T1 (migrated): each store's store_id must preserve the real, "
        "lowercase-d <StoreId> value -- the current uppercase-only parser "
        f"still silently loses it. Got: {[s.store_id for s in stores]!r}."
    )

    # Narrow, identity-specific composed-seam assertion: once identity is
    # correctly preserved, validate_stores() must not hard-fail on any of
    # it. Deliberately not asserting hard_failed is False outright -- this
    # 3-store excerpt's other fields are not independently guaranteed
    # exhaustive against every other unrelated validation rule.
    outcome = validate_stores(stores)
    assert not any(
        ("empty chain_id" in reason)
        or ("empty subchain_id" in reason)
        or ("empty store_id" in reason)
        for reason in outcome.hard_fail_reasons
    ), (
        "T1 (migrated): no hard-fail reason may concern chain_id, "
        "subchain_id, or store_id emptiness once identity is correctly "
        f"preserved -- got hard_fail_reasons={outcome.hard_fail_reasons!r}."
    )

# T2/T9's old inequality diagnostic (H. Cohen vs. a genuinely-empty Stores
# document) was intentionally removed from here once superseded -- see this
# file's module docstring for where its permanent replacement lives.
