"""Rami Levy Phase 1A collector: Stores and PriceFull only.

Modules:
- config.py -- chain-specific configuration (provider base URL, account).
- session.py -- login/CSRF/cookie handling for the authenticated portal.
- discovery.py -- pure filename-token matching against an already-fetched
  directory listing (see session.py for the network call itself).
- download.py -- fetch bytes for a discovered file via the session.
- transport.py -- content-aware gzip/ZIP detection and safe extraction.
- parse.py -- parse transport-normalized XML into source-faithful Raw
  records, including PriceFull schema-family detection (see docs/adr/0007).
- validate.py -- semantic validation of parsed records.
- records.py -- plain dataclasses shared by the above.
- run.py -- orchestrates one Phase 1A run.

Scope is deliberately limited to Rami Levy Stores and PriceFull. No other
chain, file category, database, or normalized cross-chain model is
implemented here. See docs/adr/0006 for the provider-endpoint vendor-risk
note (Rami Levy's officially published hostname currently fails standard
TLS hostname verification; this collector uses the provider's own
TLS-valid canonical hostname instead), and docs/adr/0007 for why PriceFull
is parsed as two distinct source schema families rather than one merged
model.
"""
