"""SmartCart Ingestion TDD -- T2/T9 observability: the composed Stores path
must distinguish RECOGNIZED_EMPTY, RECOGNIZED_NONEMPTY, NONEMPTY_UNRECOGNIZED,
and UNKNOWN_UNCLASSIFIED (frozen contract; exact carrier field/type names are
NOT frozen).

INITIAL RED CYCLE NOTICE: the production seam this file targets --
`smartcart.collectors.rami_levy.parse.analyze_stores_xml()` and a structural
carrier on `FileOutcome` -- does not exist yet. This file intentionally
imports the existing `parse`/`run`/`records` MODULES (which do exist) rather
than the not-yet-existing symbols themselves, so collection never fails on a
missing import. Each test instead calls a small local helper
(`_analyze()`/`_require_structural_carrier()`) that explicitly fails the test
with a `SEAM/API MISSING` message the first time the missing seam is
actually needed. This is expected, permanent RED for this cycle -- once the
production seam exists, the SAME tests must proceed past that guard into the
semantic classification assertions below it, with no test-code change beyond
possibly reconciling the two provisional accessor names
(`result.classification` / `result.unsupported_structure_count` for
analyze_stores_xml, and `outcome.structural_classification` /
`outcome.unsupported_structure_count` for FileOutcome) to whatever the real
implementation actually names them -- those two names are this test's own
placeholder, NOT approved production API.

Four semantic states under test (frozen names, per this task's contract):
RECOGNIZED_EMPTY, RECOGNIZED_NONEMPTY, NONEMPTY_UNRECOGNIZED,
UNKNOWN_UNCLASSIFIED. `_classification_name()` below accepts either a plain
string or an Enum-like value (via `.name`) for whichever shape the real
carrier ends up using.

This file does not modify, weaken, or duplicate T1, T2/T9's existing
distinguishability test, or T3 -- it is new, additive, permanent coverage
for a different (currently nonexistent) seam.
"""

from __future__ import annotations

import gzip
from datetime import UTC, datetime

import pytest

from smartcart.collectors.rami_levy import download, run
from smartcart.collectors.rami_levy import parse as rl_parse
from smartcart.collectors.rami_levy import transport as rl_transport
from smartcart.collectors.rami_levy import validate as rl_validate

# ---------------------------------------------------------------------------
# Seam-missing-safe helpers
# ---------------------------------------------------------------------------


def _analyze(normalized: bytes):
    """Call the not-yet-existing analyze_stores_xml(), failing explicitly
    (not via ImportError at collection time) if the seam does not exist."""
    if not hasattr(rl_parse, "analyze_stores_xml"):
        pytest.fail(
            "SEAM/API MISSING: smartcart.collectors.rami_levy.parse."
            "analyze_stores_xml does not exist yet. parse_stores_xml() "
            "(the compatibility records-only API) is unaffected and remains "
            "untouched -- this failure is expected for the initial RED cycle "
            "of the T2/T9 observability contract."
        )
    return rl_parse.analyze_stores_xml(normalized)


def _classification_name(value: object) -> object:
    """Accept either a plain string state name or an Enum-like value
    exposing `.name` -- the carrier's exact type is not frozen."""
    return getattr(value, "name", value)


def _require_structural_carrier(outcome) -> None:
    """Fail explicitly if FileOutcome does not yet carry the structural
    observation -- the composed run_stores()/FileOutcome seam is not
    implemented yet, exactly like analyze_stores_xml() above."""
    if not hasattr(outcome, "structural_classification"):
        pytest.fail(
            "SEAM/API MISSING: FileOutcome has no 'structural_classification' "
            "field yet (a provisional, non-frozen name used only by this "
            "test) -- run_stores() does not yet propagate the structural "
            "observation into the composed FileOutcome. Expected for the "
            "initial RED cycle."
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# --- A. SUPPORTED EMPTY ------------------------------------------------
#
# PROVENANCE: SYNTHETIC_TEST_FIXTURE
# No physical-artifact source. Mirrors the shape already established by
# TRUE_EMPTY_STORES_XML in tests/collectors/rami_levy/test_batch1_stores_regressions.py
# and EMPTY_STORES_XML in tests/collectors/rami_levy/test_parse.py (not
# imported from either, to keep this file self-contained, per this
# engagement's established convention). The <SubChains> element is PRESENT
# (positive recognition of the supported Stores envelope) but has zero
# children -- this is the "envelope recognized, genuinely zero records"
# case, distinct from fixture D below where no <SubChains> element exists
# at all.
_RECOGNIZED_EMPTY_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>7290058140886</ChainID>"
    "<ChainName>Test Chain</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "<SubChains></SubChains>"
    "</Root>"
)
RECOGNIZED_EMPTY_STORES_XML = b"\xff\xfe" + _RECOGNIZED_EMPTY_STORES_XML_TEXT.encode("utf-16-le")
RECOGNIZED_EMPTY_STORES_FILENAME = "Stores7290058140886-000-20260907-050500.xml"

# --- B. SUPPORTED NON-EMPTY ---------------------------------------------
#
# PROVENANCE: SYNTHETIC_TEST_FIXTURE
# No physical-artifact source. Mirrors the shape already established by
# VALID_STORES_XML in tests/collectors/rami_levy/test_parse.py (uppercase-D
# casing, SubChains>SubChain>Stores>Store nesting, one real-shaped Store
# record) -- not imported, kept self-contained.
_RECOGNIZED_NONEMPTY_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>7290058140886</ChainID>"
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
RECOGNIZED_NONEMPTY_STORES_XML = b"\xff\xfe" + _RECOGNIZED_NONEMPTY_STORES_XML_TEXT.encode(
    "utf-16-le"
)
RECOGNIZED_NONEMPTY_STORES_FILENAME = "Stores7290058140886-001-20260907-050501.xml"

# --- C. H. COHEN PHYSICAL EVIDENCE --------------------------------------
#
# PROVENANCE: PHYSICAL_FULL_PAYLOAD_VERBATIM_REENCODED
# Entity/source: H. Cohen (Het Cohen), Wave 3. Physical artifact ID:
#   W3-ART-0001. Original source path (held evidence, NOT modified):
#   ~/smartcart-data/source-diversity/wave3/artifacts/H_Cohen/
#   StoresFull7290455000004-000-202609140627-000.xml.gz
# Identical, verbatim decompressed payload to the copy already established
#   in tests/collectors/rami_levy/test_batch1_stores_regressions.py (not
#   imported from there, kept self-contained per this engagement's
#   convention) -- the entire real 5-<Branch> document, re-gzip-compressed
#   at test time (original gzip container bytes are NOT reproduced, only
#   the decompressed content is verbatim -- see that file's own provenance
#   note for the same disclaimer).
# Discovery-filename note: H. Cohen's REAL filename
#   ("StoresFull7290455000004-000-202609140627-000.xml.gz") does not match
#   discovery.py's _STORES_RE at all (wrong prefix "StoresFull" vs
#   "Stores", and a ".xml.gz" double extension vs the required literal
#   ".xml") -- this is the same class of discovery-layer gap already
#   recorded for other entities in
#   ~/smartcart-data/coverage-closure/test-gap-audit/
#   batch1_discovery_gap_findings.json. Consistent with that precedent and
#   with this task's explicit "H. Cohen schema support is out of scope"
#   instruction, a synthetic discovery-compliant filename carrying the
#   same real chain_id numerals is used for the composed run_stores() test
#   below, isolating the structural-observation claim from that separate,
#   unaddressed discovery question.
_H_COHEN_REAL_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<Store Date="14/09/26" Time="06:27:02">\n'
    '  <Branches>\n'
    '    <Branch>\n'
    '      <ChainID>7290455000004</ChainID>\n'
    '      <SubChainID>001</SubChainID>\n'
    '      <StoreID>001</StoreID>\n'
    '      <BikoretNo />\n'
    '      <StoreType>1</StoreType>\n'
    '      <ChainName />\n'
    '      <SubChainName />\n'
    '      <StoreName>המלאכה</StoreName>\n'
    '      <Address> </Address>\n'
    '      <City />\n'
    '      <ZIPCode />\n'
    '      <LastUpdateDate>01/01/0001 00:00:00</LastUpdateDate>\n'
    '      <Latitude />\n'
    '      <Longitude />\n'
    '    </Branch>\n'
    '    <Branch>\n'
    '      <ChainID>7290455000004</ChainID>\n'
    '      <SubChainID>001</SubChainID>\n'
    '      <StoreID>035</StoreID>\n'
    '      <BikoretNo />\n'
    '      <StoreType />\n'
    '      <ChainName />\n'
    '      <SubChainName />\n'
    '      <StoreName>סניף קליק וסע</StoreName>\n'
    '      <Address> </Address>\n'
    '      <City />\n'
    '      <ZIPCode />\n'
    '      <LastUpdateDate>01/01/0001 00:00:00</LastUpdateDate>\n'
    '      <Latitude />\n'
    '      <Longitude />\n'
    '    </Branch>\n'
    '    <Branch>\n'
    '      <ChainID>7290455000004</ChainID>\n'
    '      <SubChainID>001</SubChainID>\n'
    '      <StoreID>045</StoreID>\n'
    '      <BikoretNo />\n'
    '      <StoreType>1</StoreType>\n'
    '      <ChainName />\n'
    '      <SubChainName />\n'
    '      <StoreName>סניף מערב נתיבות</StoreName>\n'
    '      <Address> </Address>\n'
    '      <City />\n'
    '      <ZIPCode />\n'
    '      <LastUpdateDate>01/01/0001 00:00:00</LastUpdateDate>\n'
    '      <Latitude />\n'
    '      <Longitude />\n'
    '    </Branch>\n'
    '    <Branch>\n'
    '      <ChainID>7290455000004</ChainID>\n'
    '      <SubChainID>001</SubChainID>\n'
    '      <StoreID>065</StoreID>\n'
    '      <BikoretNo />\n'
    '      <StoreType>1</StoreType>\n'
    '      <ChainName />\n'
    '      <SubChainName />\n'
    '      <StoreName>סניף מול שדרות</StoreName>\n'
    '      <Address> </Address>\n'
    '      <City />\n'
    '      <ZIPCode />\n'
    '      <LastUpdateDate>01/01/0001 00:00:00</LastUpdateDate>\n'
    '      <Latitude />\n'
    '      <Longitude />\n'
    '    </Branch>\n'
    '    <Branch>\n'
    '      <ChainID>7290455000004</ChainID>\n'
    '      <SubChainID>001</SubChainID>\n'
    '      <StoreID>075</StoreID>\n'
    '      <BikoretNo />\n'
    '      <StoreType>1</StoreType>\n'
    '      <ChainName />\n'
    '      <SubChainName />\n'
    '      <StoreName>סניף רימון</StoreName>\n'
    '      <Address> </Address>\n'
    '      <City />\n'
    '      <ZIPCode />\n'
    '      <LastUpdateDate>01/01/0001 00:00:00</LastUpdateDate>\n'
    '      <Latitude />\n'
    '      <Longitude />\n'
    '    </Branch>\n'
    '  </Branches>\n'
    '</Store>\n'
)
H_COHEN_BRANCH_COUNT = 5


def _h_cohen_real_gzip_bytes() -> bytes:
    return gzip.compress(_H_COHEN_REAL_XML.encode("utf-8"))


H_COHEN_SYNTHETIC_DISCOVERY_FILENAME = "Stores7290455000004-000-20260914-062702.xml"

# --- D. UNKNOWN ----------------------------------------------------------
#
# PROVENANCE: SYNTHETIC_TEST_FIXTURE
# No physical-artifact source; not motivated by any specific real evidence.
#   Smallest possible document that: produces zero supported Store records
#   (no <SubChain>/<Store> anywhere -- root.findall(".//SubChain") is
#   empty), does NOT positively match the supported envelope (no
#   <SubChains> element at all, unlike fixture A which has it present but
#   childless), and contains no <Branches>/<Branch> structure (so it must
#   not be classified as NONEMPTY_UNRECOGNIZED either).
_UNKNOWN_STORES_XML_TEXT = (
    "<Root>"
    "<ChainID>7290058140886</ChainID>"
    "<ChainName>Test Chain</ChainName>"
    "<LastUpdateDate>2026-09-07</LastUpdateDate>"
    "<LastUpdateTime>05:05:00.317</LastUpdateTime>"
    "</Root>"
)
UNKNOWN_STORES_XML = b"\xff\xfe" + _UNKNOWN_STORES_XML_TEXT.encode("utf-16-le")
UNKNOWN_STORES_FILENAME = "Stores7290058140886-002-20260907-050502.xml"


# ---------------------------------------------------------------------------
# A/B/C/D -- analyze_stores_xml() seam
# ---------------------------------------------------------------------------


def test_a_recognized_empty_envelope_classification() -> None:
    """CASE A: supported-empty envelope -> RECOGNIZED_EMPTY,
    unsupported_structure_count == 0. Positive recognition of the envelope
    itself (the <SubChains> container being present), not of any record
    within it -- no SubChain/Store record is required to exist.
    """
    normalized = rl_transport.normalize(RECOGNIZED_EMPTY_STORES_XML)
    result = _analyze(normalized)

    assert _classification_name(result.classification) == "RECOGNIZED_EMPTY"
    assert result.unsupported_structure_count == 0


def test_b_recognized_nonempty_envelope_classification() -> None:
    """CASE B: supported, non-empty Stores data -> RECOGNIZED_NONEMPTY,
    unsupported_structure_count == 0."""
    normalized = rl_transport.normalize(RECOGNIZED_NONEMPTY_STORES_XML)
    result = _analyze(normalized)

    assert _classification_name(result.classification) == "RECOGNIZED_NONEMPTY"
    assert result.unsupported_structure_count == 0


def test_c_h_cohen_nonempty_unrecognized_fails_closed() -> None:
    """CASE C: real H. Cohen physical evidence -> NONEMPTY_UNRECOGNIZED,
    unsupported_structure_count == 5 (the 5 observed Branch structures),
    and the composed validation must still fail closed. Branch field
    content is never parsed -- only structural (Branches>Branch) presence
    is asserted.
    """
    normalized = rl_transport.normalize(_h_cohen_real_gzip_bytes())
    result = _analyze(normalized)

    assert _classification_name(result.classification) == "NONEMPTY_UNRECOGNIZED"
    assert result.unsupported_structure_count == H_COHEN_BRANCH_COUNT

    outcome = rl_validate.validate_stores(rl_parse.parse_stores_xml(normalized))
    assert outcome.hard_failed is True


def test_d_unknown_unclassified_fails_closed() -> None:
    """CASE D: structurally minimal, non-enveloped, non-Branch document ->
    UNKNOWN_UNCLASSIFIED, unsupported_structure_count == 0, and the
    composed validation must still fail closed (0 records either way).
    """
    normalized = rl_transport.normalize(UNKNOWN_STORES_XML)
    result = _analyze(normalized)

    assert _classification_name(result.classification) == "UNKNOWN_UNCLASSIFIED"
    assert result.unsupported_structure_count == 0

    outcome = rl_validate.validate_stores(rl_parse.parse_stores_xml(normalized))
    assert outcome.hard_failed is True


# ---------------------------------------------------------------------------
# Composed outcome contract -- run_stores() / FileOutcome
# ---------------------------------------------------------------------------

_LISTING_FETCHED_AT = datetime(2026, 9, 15, 0, 0, 0, tzinfo=UTC)


def _run_stores_with_body(monkeypatch: pytest.MonkeyPatch, filename: str, body: bytes):
    monkeypatch.setattr(download, "download_bytes", lambda session, fname: body)
    rows = [{"fname": filename, "time": "2026-09-15T00:00:00Z"}]
    return run.run_stores(
        session=None,  # unused: download.download_bytes is monkeypatched above
        rows=rows,
        listing_fetched_at=_LISTING_FETCHED_AT,
    )


def test_composed_recognized_empty_survives_to_file_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The RECOGNIZED_EMPTY classification must be observable on the
    composed FileOutcome returned by run_stores() -- not just at the bare
    parse/validate seam."""
    _, outcome = _run_stores_with_body(
        monkeypatch, RECOGNIZED_EMPTY_STORES_FILENAME, RECOGNIZED_EMPTY_STORES_XML
    )
    _require_structural_carrier(outcome)

    assert _classification_name(outcome.structural_classification) == "RECOGNIZED_EMPTY"
    assert outcome.unsupported_structure_count == 0


def test_composed_h_cohen_survives_to_file_outcome_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The NONEMPTY_UNRECOGNIZED classification, and fail-closed behavior,
    must survive through run_stores() to the composed FileOutcome."""
    _, outcome = _run_stores_with_body(
        monkeypatch, H_COHEN_SYNTHETIC_DISCOVERY_FILENAME, _h_cohen_real_gzip_bytes()
    )
    _require_structural_carrier(outcome)

    assert _classification_name(outcome.structural_classification) == "NONEMPTY_UNRECOGNIZED"
    assert outcome.unsupported_structure_count == H_COHEN_BRANCH_COUNT
    assert outcome.succeeded is False


def test_composed_unknown_survives_to_file_outcome_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UNKNOWN_UNCLASSIFIED classification, and fail-closed behavior,
    must survive through run_stores() to the composed FileOutcome."""
    _, outcome = _run_stores_with_body(
        monkeypatch, UNKNOWN_STORES_FILENAME, UNKNOWN_STORES_XML
    )
    _require_structural_carrier(outcome)

    assert _classification_name(outcome.structural_classification) == "UNKNOWN_UNCLASSIFIED"
    assert outcome.unsupported_structure_count == 0
    assert outcome.succeeded is False
