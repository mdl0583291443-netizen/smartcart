# 0006. Rami Levy provider endpoint: TLS-valid hostname vs. officially published one

## Status

Accepted

## Context

Rami Levy's own price-transparency page
(https://www.rami-levy.co.il/he/price-transparency) currently publishes
`https://url.retail.publishedprices.co.il` as the login URL for its public
price-transparency data (username `RamiLevi`, no password).

Dedicated TLS reconnaissance (re-verified live, not assumed stale) found
that `url.retail.publishedprices.co.il` currently fails standard TLS
hostname verification: the certificate presented there has subject/SAN
`CN=*.publishedprices.co.il`, a single-level wildcard, which by standard
wildcard-matching rules does not cover a two-label hostname like
`url.retail.publishedprices.co.il`. This was confirmed independently with
two separate TLS clients (curl/Windows Schannel: `SEC_E_WRONG_PRINCIPAL`;
OpenSSL 3.5.7 `-verify_hostname`: `verify error:num=62:hostname mismatch`).
The certificate itself is otherwise valid (issued by SSL.com, not expired)
-- this is a hostname-coverage gap, not an expired or self-signed cert.

## Decision

SmartCart's Phase 1A Rami Levy collector uses
`https://url.publishedprices.co.il` (no `retail.` label) as its default
provider endpoint, configured once in `rami_levy/config.py` and
overridable via the `SMARTCART_RAMI_LEVY_PROVIDER_BASE_URL` environment
variable.

Evidence/rationale for this specific alternative hostname (not a guess):
- It passes full, standard TLS and hostname verification with no
  exceptions, confirmed independently with both curl and OpenSSL.
- It resolves to the same IP and is served by the same backend
  ("Cerberus Web Client" / "Public Published Prices Server") as the
  officially published hostname.
- It is independently corroborated as the provider's shared canonical
  hostname: Cofix's own official transparency page documents the same
  hostname (`url.publishedprices.co.il`) for a different tenant account
  (`SuperCofixApp`) on the identical platform.
- The public `RamiLevi` account was confirmed to authenticate
  successfully against this hostname and list live, current files
  (matching Rami Levy's own ChainID).

This collector never disables certificate verification, hostname
verification, or uses a custom trust store/pinning to reach either
hostname. If `url.publishedprices.co.il` itself ever fails standard TLS
verification, that is a `LoginError`/run-level failure to report, not a
condition to work around.

**No explicit confirmation from Rami Levy or the provider has been
obtained** that `url.publishedprices.co.il` is the intended long-term
endpoint for this specific tenant. Vendor confirmation (or a fixed
certificate on the officially published hostname) remains an open
operational item before this integration is considered fully
production-approved.

## Consequences

- The collector's default endpoint intentionally differs from what Rami
  Levy's own page currently publishes. This must be revisited if either
  hostname's TLS posture changes.
- If the officially published hostname's certificate is fixed to cover it
  (or a new officially documented hostname appears), `config.py` should be
  updated and this ADR revised accordingly.
- Should the current provider hostname ever start failing standard
  verification too, the correct response is to stop and report it (per
  Phase 1A's run-level failure handling), not to relax verification.
