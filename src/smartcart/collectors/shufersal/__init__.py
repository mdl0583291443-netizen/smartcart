"""Shufersal Phase 1A collector: Stores and PriceFull only.

Modules:
- discovery.py -- find the current Stores/PriceFull file on the official
  public Shufersal price-transparency portal (https://prices.shufersal.co.il).
- download.py -- fetch the bytes for a discovered file.
- transport.py -- verify/decompress the gzip transport layer.
- parse.py -- parse decompressed XML into source-faithful Raw records.
- validate.py -- semantic validation of parsed records.
- records.py -- plain dataclasses shared by the above.
- run.py -- orchestrates one Phase 1A run.

Scope is deliberately limited to Shufersal Stores and PriceFull. No other
chain, file category, database, or normalized cross-chain model is
implemented here.
"""
