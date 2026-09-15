"""SmartCart Ingestion TDD -- Tests First, Batch 1: T6/T7/T8.

The ONLY claim under test in this file: run_pricefull_for_store() correctly
converts a real ParseError (from a real, byte-faithful PriceFull payload)
into the composed FileOutcome failure shape (succeeded=False,
failed_stage="parse"). The general "missing required Item tag raises
ParseError" mechanism itself is already exhaustively covered by
tests/collectors/rami_levy/test_parse.py and is NOT re-tested here -- this
file exists only because no existing test exercises run.py's ParseError-
handling branch at all (only its DiscoveryError branch is currently
exercised, by test_run_integration.py).

SCOPE NOTE: the full failure shape asserted per case is succeeded=False,
failed_stage="parse", error_type="ParseError", and the specific missing
required field's name present in error_message -- no broader claim is
made. This batch does not claim general retailer or schema support beyond
that one ParseError-to-FileOutcome conversion for each of the three real
payloads exercised here.

Frozen RED Plan classification: EXPECTED_GREEN_REGRESSION for all three
cases (T6, T7, T8). Requirements: R1, R3, R6.

Test seam: run_pricefull_for_store(session, rows, store_id,
listing_fetched_at), entered directly. `download.download_bytes` is
monkeypatched to return real/byte-faithful bytes for a synthetic,
discovery-compliant filename -- discovery.find_pricefull_file() itself is
exercised normally (unmocked), only the network call underneath it is
replaced, exactly mirroring test_run_integration.py's own established
monkeypatch style (there via urllib, here one level higher since only the
download call, not the whole session/HTTP stack, needs replacing for this
claim).

IMPORTANT INCIDENTAL FINDING (not tested here, out of scope for this
batch): the REAL filenames for two of these three artifacts would NOT
actually be discovered by discovery.find_pricefull_file()'s regexes as
they exist in the held corpus --

- City Market Shops' real filename is
  "Price7290000000003-000-020-20260914-214227.gz" (starts with "Price",
  not "PriceFull" -- the discovery regex requires the literal "pricefull"
  prefix, case-insensitively, so this would not match at all).
- Meshnat Yosef's real filename is
  "PriceFull5144744100002-001-001-20260914-013004.zip" (the discovery
  regex requires a literal ".gz" suffix; this file's real extension is
  ".zip").

Both are real, held, previously-unflagged discovery-layer discrepancies
discovered while building this batch's fixtures. Neither is one of this
batch's authorized T-rows, so no test is added for either here; they are
recorded in this batch's final report for follow-up triage. To isolate
this file's actual claim (the parse-layer ParseError -> FileOutcome
conversion) from that separate, unrelated discovery-layer question, both
fixtures below use a synthetic, discovery-regex-compliant filename paired
with the real payload bytes -- see each case's own provenance note.
"""

from __future__ import annotations

import gzip
import io
import zipfile
from datetime import UTC, datetime

import pytest

from smartcart.collectors.rami_levy import download, run

_LISTING_FETCHED_AT = datetime(2026, 9, 15, 0, 0, 0, tzinfo=UTC)


# ===========================================================================
# T6 -- City Market Shops (real artifact, PriceFull family, missing bIsWeighted)
# ===========================================================================
#
# PROVENANCE: PHYSICAL_FULL_PAYLOAD_VERBATIM_REENCODED
#             WITH_SYNTHETIC_DISCOVERY_FILENAME
# T-row: T6
# Entity/source: City Market Shops, Coverage Closure Batch 6
# Physical artifact ID: B6-ART-0004
# Original source path (held evidence, NOT modified):
#   ~/smartcart-data/coverage-closure/artifacts/City_Market_Shops/
#   Price7290000000003-000-020-20260914-214227.gz
# Container/encoding, verified by direct inspection: GZIP, plain UTF-8 (no
#   BOM), standard family casing (ChainID/SubChainID/StoreID, all
#   uppercase). The real artifact contains exactly one <Item> element; that
#   one element is embedded verbatim below, byte-for-byte identical (as
#   decompressed text) to the held artifact -- it genuinely has no
#   <bIsWeighted> tag anywhere. The gzip CONTAINER bytes are NOT preserved:
#   the decompressed XML text is re-gzip-compressed at test time
#   (`gzip.compress(...)`), which does not reproduce the original
#   artifact's own compressed byte stream. The discovery filename used by
#   this test is SYNTHETIC, not the artifact's real filename -- see this
#   module's own docstring and
#   ~/smartcart-data/coverage-closure/test-gap-audit/
#   batch1_discovery_gap_findings.json for why.
# Filename note: the REAL filename ("Price...", not "PriceFull...") would
#   not pass discovery's regex at all (see module docstring) -- a
#   synthetic "PriceFull"-prefixed filename carrying the SAME real
#   chain/subchain/store numerals is used here so discovery succeeds and
#   the real ParseError is what's actually observed, isolating this file's
#   one claim from that separate, unrelated finding.
_CITY_MARKET_SHOPS_REAL_XML = (
    "<Root>\n"
    "    <ChainID>7290000000003</ChainID>\n"
    "    <SubChainID>000</SubChainID>\n"
    "    <StoreID>020</StoreID>\n"
    "    <BikoretNo>4</BikoretNo>\n"
    "    <Items>\n"
    "        <Item>\n"
    "            <PriceUpdateTime>2026-09-14T21:22:50.000</PriceUpdateTime>\n"
    "            <ItemCode>1000</ItemCode>\n"
    "            <LastSaleDateTime>2026-09-14T21:22:00.000</LastSaleDateTime>\n"
    "            <ItemType>0</ItemType>\n"
    "            <ItemName>מכלת</ItemName>\n"
    "            <ManufactureName></ManufactureName>\n"
    "            <ManufactureCountry></ManufactureCountry>\n"
    "            <ManufactureItemDescription>מכלת</ManufactureItemDescription>\n"
    "            <UnitQty></UnitQty>\n"
    "            <Quantity>0</Quantity>\n"
    "            <UnitOfMeasure></UnitOfMeasure>\n"
    "            <QtyInPackage/>\n"
    "            <ItemPrice>20.00</ItemPrice>\n"
    "            <UnitOfMeasurePrice></UnitOfMeasurePrice>\n"
    "            <AllowDiscount>1</AllowDiscount>\n"
    "            <ItemStatus>1</ItemStatus>\n"
    "        </Item>\n"
    "    </Items>\n"
    "</Root>"
)
_CITY_MARKET_SHOPS_FILENAME = "PriceFull7290000000003-000-020-20260914-214227.gz"
_CITY_MARKET_SHOPS_STORE_ID = "020"


def _city_market_shops_bytes() -> bytes:
    return gzip.compress(_CITY_MARKET_SHOPS_REAL_XML.encode("utf-8"))


# ===========================================================================
# T7 -- Meshnat Yosef (real artifact, PriceFull family, missing LastSaleDateTime)
# ===========================================================================
#
# PROVENANCE: PHYSICAL_PAYLOAD_VERBATIM_EXCERPT_REPACKED
#             WITH_SYNTHETIC_DISCOVERY_FILENAME
# T-row: T7
# Entity/source: Meshnat Yosef, Coverage Closure Batch 6/7
# Physical artifact ID: B7-ART-0006
# Original source path (held evidence, NOT modified):
#   ~/smartcart-data/coverage-closure/artifacts/Meshnat_Yosef/
#   PriceFull5144744100002-001-001-20260914-013004.zip
# Container/encoding, verified by direct inspection: ZIP (single member),
#   plain UTF-8 (no BOM), standard family root casing
#   (ChainID/SubChainID/StoreID, uppercase). NOT a complete copy: the real
#   file holds many items; only the FIRST real <Item> element is included
#   below -- an EXCERPT, truncated from the larger real document, no
#   invented content within what IS included. That included item
#   genuinely has no <LastSaleDateTime> tag (required-tag evaluation order
#   in _parse_pricefull_standard reaches LastSaleDateTime before
#   ManufactureName, so this is the tag that actually raises first, even
#   though the file separately also uses "ManufacturerName" rather than
#   "ManufactureName" throughout). The original ZIP container is NOT
#   preserved: this excerpt is REPACKED into a freshly-built ZIP archive
#   (`zipfile.ZipFile(..., ZIP_DEFLATED)`) with a different internal
#   member name than the original, producing different compressed bytes
#   than the held artifact's own ZIP stream. The discovery filename used
#   by this test is SYNTHETIC, not the artifact's real filename -- see
#   this module's own docstring and
#   ~/smartcart-data/coverage-closure/test-gap-audit/
#   batch1_discovery_gap_findings.json for why.
# Filename note: the REAL filename ends ".zip", which would not pass
#   discovery's regex (literal ".gz" suffix required) -- a synthetic
#   ".gz"-suffixed filename is used here so discovery succeeds. This
#   specific gz-named-but-actually-ZIP combination is not fabricated for
#   this test: it mirrors an already-established real phenomenon in this
#   corpus (Zol VeBegadol and others; see the Engine Compatibility Audit),
#   and transport.normalize() detects container by magic bytes, never by
#   filename extension, so this is a faithful real-world shape.
_MESHNAT_YOSEF_REAL_XML = (
    '<?xml version="1.0" encoding="utf-8"?><Root>\n'
    "    <ChainID>5144744100002</ChainID>\n"
    "    <SubChainID>001</SubChainID>\n"
    "    <StoreID>1</StoreID>\n"
    "    <BikoretNo>0</BikoretNo>\n"
    "\t<Items>\n"
    "<Item>\n"
    "\t\t<PriceUpdateTime>2026-09-13T22:29:16.000</PriceUpdateTime>\n"
    "\t\t<ItemCode>7290116536774</ItemCode>\n"
    "\t\t<ItemType>1</ItemType>\n"
    "\t\t<ItemName>חטיף בר פריך ממולא קרם נוגט בציפוי שוקולד - קליק אין {מ.מ.}</ItemName>\n"
    "\t\t<ManufacturerName>לא ידוע</ManufacturerName>\n"
    "\t\t<ManufactureCountry>לא ידוע</ManufactureCountry>\n"
    "\t\t<ManufacturerItemDescription>חטיף בר פריך ממולא קרם נוגט בציפוי שוקולד - קליק "
    "אין {מ.מ.}</ManufacturerItemDescription>\n"
    "\t\t<UnitQty></UnitQty>\n"
    "\t\t<Quantity></Quantity>\n"
    "\t\t<UnitOfMeasure>null</UnitOfMeasure>\n"
    "\t\t<QtyInPackage>לא ידוע</QtyInPackage>\n"
    "\t\t<ItemPrice>3.9</ItemPrice>\n"
    "\t\t<UnitOfMeasurePrice>3.9</UnitOfMeasurePrice>\n"
    "\t\t<AllowDiscount>0</AllowDiscount>\n"
    "\t\t<ItemStatus>1</ItemStatus>\n"
    "\t  </Item>\n"
    "\t</Items>\n"
    "</Root>"
)
_MESHNAT_YOSEF_FILENAME = "PriceFull5144744100002-001-001-20260914-013004.gz"
_MESHNAT_YOSEF_STORE_ID = "001"


def _meshnat_yosef_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("PriceFull5144744100002-001-001-20260914-013004.xml", _MESHNAT_YOSEF_REAL_XML)
    return buf.getvalue()


# ===========================================================================
# T8 -- Politzer (real artifact, mixed-casing, missing ManufactureName)
# ===========================================================================
#
# PROVENANCE: PHYSICAL_PAYLOAD_VERBATIM_EXCERPT_REPACKED
# T-row: T8
# Entity/source: Politzer, Wave 1
# Physical artifact ID: ART-0020
# Original source path (held evidence, NOT modified):
#   ~/smartcart-data/source-diversity/wave1/artifacts/Politzer/
#   PriceFull7291059100008-001-001-20260914-001008.gz
# Container/encoding, verified by direct inspection: GZIP, plain UTF-8 (no
#   BOM), MIXED root casing -- ChainID/SubChainID uppercase, StoreId
#   lowercase -- which still routes to the standard-family parser (root
#   has a <ChainID> tag). NOT a complete copy: the real file holds many
#   items; only the FIRST real <Item> element is included below -- an
#   EXCERPT, truncation only, no invented content within what IS included.
#   That item genuinely has no literal <ManufactureName> tag (it uses
#   <ManufacturerName>, the online family's spelling, instead -- a
#   different, ElementTree-exact-match-relevant tag name). The original
#   gzip stream is NOT preserved: this excerpt is REPACKED via a fresh
#   `gzip.compress(...)` call at test time, producing different compressed
#   bytes than the held artifact's own gzip stream. The real filename IS
#   retained verbatim for this one case (no synthetic substitution) since
#   it already matches discovery's regex.
# Filename note: the real filename already matches discovery's regex
#   exactly (starts "PriceFull", ends ".gz") -- used verbatim, no synthetic
#   substitution needed for this one case.
_POLITZER_REAL_XML = (
    "<Root>\n"
    "  <ChainID>7291059100008</ChainID>\n"
    "  <SubChainID>001</SubChainID>\n"
    "  <StoreId>001</StoreId>\n"
    "  <BikoretNo>4</BikoretNo>\n"
    "  <Items>\n"
    "    <Item>\n"
    "      <PriceUpdateTime>2026-08-12T08:17:51.000</PriceUpdateTime>\n"
    "      <ItemCode>7290000000135</ItemCode>\n"
    "      <LastSaleDateTime>2026-07-21T18:35:09.000</LastSaleDateTime>\n"
    "      <ItemType>1</ItemType>\n"
    "      <ItemName>משמש</ItemName>\n"
    "      <ManufacturerName>לא ידוע</ManufacturerName>\n"
    "      <ManufactureCountry>לא ידוע</ManufactureCountry>\n"
    "      <ManufacturerItemDescription>משמש</ManufacturerItemDescription>\n"
    "      <UnitQty>יחידות</UnitQty>\n"
    "      <Quantity>1.00</Quantity>\n"
    "      <UnitOfMeasure>יחידה   </UnitOfMeasure>\n"
    "      <bIsWeighted>1</bIsWeighted>\n"
    "      <QtyInPackage>לא ידוע</QtyInPackage>\n"
    "      <ItemPrice>16.90</ItemPrice>\n"
    "      <UnitOfMeasurePrice>16.90</UnitOfMeasurePrice>\n"
    "      <AllowDiscount>1</AllowDiscount>\n"
    "      <ItemStatus/>\n"
    "    </Item>\n"
    "  </Items>\n"
    "</Root>"
)
_POLITZER_FILENAME = "PriceFull7291059100008-001-001-20260914-001008.gz"
_POLITZER_STORE_ID = "001"


def _politzer_bytes() -> bytes:
    return gzip.compress(_POLITZER_REAL_XML.encode("utf-8"))


_CASES = [
    pytest.param(
        _CITY_MARKET_SHOPS_FILENAME,
        _CITY_MARKET_SHOPS_STORE_ID,
        _city_market_shops_bytes,
        "bIsWeighted",
        id="T6-city-market-shops-missing-bIsWeighted",
    ),
    pytest.param(
        _MESHNAT_YOSEF_FILENAME,
        _MESHNAT_YOSEF_STORE_ID,
        _meshnat_yosef_bytes,
        "LastSaleDateTime",
        id="T7-meshnat-yosef-missing-LastSaleDateTime",
    ),
    pytest.param(
        _POLITZER_FILENAME,
        _POLITZER_STORE_ID,
        _politzer_bytes,
        "ManufactureName",
        id="T8-politzer-missing-ManufactureName",
    ),
]


@pytest.mark.parametrize("filename,store_id,body_factory,missing_tag", _CASES)
def test_t6_t7_t8_run_pricefull_for_store_converts_real_parse_error_to_file_outcome(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    store_id: str,
    body_factory: object,
    missing_tag: str,
) -> None:
    """EXPECTED_GREEN_REGRESSION (T6/T7/T8). Requirements: R1, R3, R6.

    Semantic assertions only, per the batch instructions -- exact
    incidental exception wording is recorded (for provenance/debugging)
    but not asserted on beyond confirming the named missing tag appears in
    it. No persistence/current-state claim is made: run.py has no
    production persistence bridge.
    """
    body = body_factory()  # type: ignore[operator]
    monkeypatch.setattr(download, "download_bytes", lambda session, fname: body)

    rows = [{"fname": filename, "time": "2026-09-15T00:00:00Z"}]
    items, outcome = run.run_pricefull_for_store(
        session=None,  # unused: download.download_bytes is monkeypatched above
        rows=rows,
        store_id=store_id,
        listing_fetched_at=_LISTING_FETCHED_AT,
    )

    assert items == []
    assert outcome.succeeded is False
    assert outcome.failed_stage == "parse"
    assert outcome.error_type == "ParseError"
    assert missing_tag in (outcome.error_message or "")
