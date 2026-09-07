"""Per-supermarket-chain data collectors.

Each chain's collector lives in its own subpackage (e.g. `shufersal`) and is
implemented independently against that chain's official/public data source.
There is intentionally no shared collector interface, base class, or plugin
framework in Phase 1A -- see docs/adr/0003 and docs/adr/0004.
"""
