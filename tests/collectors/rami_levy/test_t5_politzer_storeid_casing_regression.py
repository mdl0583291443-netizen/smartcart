"""SmartCart Ingestion TDD -- Tests First: T5.

The ONLY claim under test in this file: for a standard-family PriceFull
document (dispatched via root <ChainID> presence) whose root identity block
uses the OTHER family's casing for just the store tag (<StoreId>, not
<StoreID>) -- a genuine, real, observed mixed-casing variant -- the parser
must still preserve the source-native store identity value ("001"), for
either observed casing. It must not silently drop it to "".

Frozen requirement (T5): for the observed PriceFull identity field,
source-native store identity must be preserved when represented by either
observed casing, StoreID or StoreId. Requirement: the derived fixture's
<StoreId>001</StoreId> must parse to item.store_id == "001".

Current behavior is known (this session's own direct execution against the
real bytes, see below) to instead return "" -- _parse_pricefull_standard()
looks up only the literal tag name "StoreID" (case-sensitive), so a root
carrying "StoreId" is silently treated as if the tag were absent. This test
intentionally asserts the DESIRED behavior ("001"), not the current broken
one (""), so it is expected to fail RED against today's implementation.

Do NOT confuse this with T8 (test_batch1_run_parse_error_regressions.py):
T8 proves the physical, UNMODIFIED Politzer PriceFull artifact fails loudly
with ParseError on a missing <ManufactureName> tag. T5 asks an entirely
different, narrower question -- given a document that reaches
_parse_pricefull_standard()'s return path at all, is the mixed-casing root
identity handled correctly? -- and is therefore evaluated against a
necessarily-modified derived fixture (see PROVENANCE below), never against
T8's own unmodified fixture. T8's own test/fixture/assertions are untouched
by this file and remain the physical-artifact ParseError regression.

PROVENANCE: PHYSICAL_PAYLOAD_DERIVED_DIAGNOSTIC_FIXTURE.

Original source path (held evidence, NOT modified):
  ~/smartcart-data/source-diversity/wave1/artifacts/Politzer/
  PriceFull7291059100008-001-001-20260914-001008.gz
(the exact same physical artifact T8's own provenance note cites as
ART-0020). Container/encoding, verified by direct inspection this session:
GZIP, decompressed text is UTF-8 with a BOM (b"\\xef\\xbb\\xbf"), CRLF line
endings, no <?xml?> declaration, 10,812 real <Item> elements.

What is PHYSICAL/verbatim below, extracted this session by directly
decompressing the real artifact and slicing out the exact substrings
(byte-for-byte, including original CRLF line endings and indentation, no
manual retyping):
  - The entire root identity block: <ChainID>7291059100008</ChainID>,
    <SubChainID>001</SubChainID>, <StoreId>001</StoreId> (the real, observed
    lowercase-d casing -- confirmed by direct execution this session: this
    exact document contains exactly one "StoreId" substring and zero
    "StoreID" substrings anywhere in its 9,419,644 decompressed bytes), and
    <BikoretNo>4</BikoretNo>.
  - Exactly one real <Item> element: the document's actual first Item,
    including every one of its real field values verbatim (PriceUpdateTime,
    ItemCode, LastSaleDateTime, ItemType, ItemName, ManufacturerName,
    ManufactureCountry, ManufacturerItemDescription, UnitQty, Quantity,
    UnitOfMeasure, bIsWeighted, QtyInPackage, ItemPrice,
    UnitOfMeasurePrice, AllowDiscount, ItemStatus).

What is SYNTHETIC below (additive only -- nothing real is renamed or
removed): two extra tags, <ManufactureName> and <ManufactureItemDescription>,
appended to the one real Item alongside its real, untouched
<ManufacturerName>/<ManufacturerItemDescription> tags. Direct execution this
session confirmed the real item has NEITHER of these two standard-family-
required tags (T8's own docstring only names ManufactureName; this session
additionally found ManufactureItemDescription is equally absent from every
one of the document's 10,812 items) -- so, unmodified, this document raises
ParseError on item 0 before _parse_pricefull_standard() ever returns
anything, making the root-identity-casing question unobservable through the
physical artifact alone. These two synthetic tags exist ONLY to get past
that known, unrelated, already-covered-by-T8 required-tag blocker; their
placeholder text ("SYNTHETIC_PLACEHOLDER_NOT_PHYSICAL") is not, and does not
claim to be, real source data. Their presence is required only because
parse.py's per-Item required-tag checks run before the function can return
at all -- they carry no meaning for, and are not read by, the T5 claim
itself (store_id handling).

This fixture is NOT byte-faithful: unlike T6/T7/T8's re-gzipped-but-
otherwise-unmodified excerpts, this fixture's decompressed text has two
tags added that do not exist in the physical artifact, and is re-encoded
(UTF-8 + BOM) rather than reusing the original compressed byte stream. This
test does not claim general Politzer schema support, does not claim
ManufactureName/ManufactureItemDescription are optional in production, does
not implement or claim generic case-insensitive XML parsing, and does not
address discovery behavior or StoreId/StoreID precedence when both are
present on the same root -- all of those are explicitly out of scope for
T5.
"""

from __future__ import annotations

from smartcart.collectors.rami_levy import parse

# Verbatim root identity block + verbatim first real <Item>, with exactly
# two synthetic, additive-only tags appended (see PROVENANCE above).
_POLITZER_DERIVED_XML_TEXT = (
    "<Root>\r\n"
    "  <ChainID>7291059100008</ChainID>\r\n"
    "  <SubChainID>001</SubChainID>\r\n"
    "  <StoreId>001</StoreId>\r\n"
    "  <BikoretNo>4</BikoretNo>\r\n"
    "  <Items>\r\n"
    "    <Item>\r\n"
    "      <PriceUpdateTime>2026-08-12T08:17:51.000</PriceUpdateTime>\r\n"
    "      <ItemCode>7290000000135</ItemCode>\r\n"
    "      <LastSaleDateTime>2026-07-21T18:35:09.000</LastSaleDateTime>\r\n"
    "      <ItemType>1</ItemType>\r\n"
    "      <ItemName>משמש</ItemName>\r\n"
    "      <ManufacturerName>לא ידוע</ManufacturerName>\r\n"
    "      <ManufactureCountry>לא ידוע</ManufactureCountry>\r\n"
    "      <ManufacturerItemDescription>משמש</ManufacturerItemDescription>\r\n"
    "      <UnitQty>יחידות</UnitQty>\r\n"
    "      <Quantity>1.00</Quantity>\r\n"
    "      <UnitOfMeasure>יחידה   </UnitOfMeasure>\r\n"
    "      <bIsWeighted>1</bIsWeighted>\r\n"
    "      <QtyInPackage>לא ידוע</QtyInPackage>\r\n"
    "      <ItemPrice>16.90</ItemPrice>\r\n"
    "      <UnitOfMeasurePrice>16.90</UnitOfMeasurePrice>\r\n"
    "      <AllowDiscount>1</AllowDiscount>\r\n"
    "      <ItemStatus/>\r\n"
    # --- SYNTHETIC, additive-only: absent from the real item; added solely
    # --- to get past the unrelated, already-covered-by-T8 required-tag
    # --- blocker (see PROVENANCE above). Not read by this test's assertions.
    "      <ManufactureName>SYNTHETIC_PLACEHOLDER_NOT_PHYSICAL</ManufactureName>\r\n"
    "      <ManufactureItemDescription>SYNTHETIC_PLACEHOLDER_NOT_PHYSICAL</ManufactureItemDescription>\r\n"
    "    </Item>\r\n"
    "  </Items>\r\n"
    "</Root>"
)

_POLITZER_DERIVED_XML_BYTES = b"\xef\xbb\xbf" + _POLITZER_DERIVED_XML_TEXT.encode("utf-8")


def test_t5_politzer_lowercase_storeid_casing_is_preserved_not_dropped() -> None:
    """EXPECTED_SEMANTIC_RED against current implementation. Requirement:
    T5 frozen requirement (see module docstring).

    Asserts the DESIRED behavior: store_id == "001", the real, source-
    native value carried by the root's <StoreId> tag. Also asserts
    chain_id/subchain_id to prove the fixture genuinely reached and
    returned from the standard-family parser path (dispatched via the
    real, verbatim <ChainID> tag), not merely that no exception was
    raised.
    """
    items = parse.parse_pricefull_xml(_POLITZER_DERIVED_XML_BYTES)

    assert len(items) == 1
    item = items[0]
    assert item.chain_id == "7291059100008"
    assert item.subchain_id == "001"
    assert item.store_id == "001"
