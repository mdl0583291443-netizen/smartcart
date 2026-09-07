"""Chain-specific configuration for the Rami Levy Phase 1A collector.

This is deliberately a small module of constants plus one lookup function,
not a generic settings framework -- there is no existing project-wide
config-loading convention to extend (see README/.env.example), so this
follows the same minimal `os.environ.get(...)` style used elsewhere in the
project rather than introducing a new dependency (e.g. pydantic-settings).

Endpoint note (see docs/adr/0006-rami-levy-provider-endpoint.md):
Rami Levy's own price-transparency page currently publishes
`https://url.retail.publishedprices.co.il` as the login URL. That hostname
currently fails standard TLS hostname verification because the presented
certificate (`CN=*.publishedprices.co.il`) is a single-level wildcard that
does not cover a two-label hostname. This collector instead defaults to
`https://url.publishedprices.co.il` -- the same provider's canonical
hostname, which passes full standard TLS/hostname verification and was
confirmed (in reconnaissance) to serve the identical account and data.
This default must never be silently worked around with disabled
certificate/hostname verification if the officially published hostname is
used instead; see the ADR for the full rationale and its open items.
"""

from __future__ import annotations

import os

DEFAULT_PROVIDER_BASE_URL = "https://url.publishedprices.co.il"
PROVIDER_BASE_URL_ENV_VAR = "SMARTCART_RAMI_LEVY_PROVIDER_BASE_URL"

# Public, password-less account documented on Rami Levy's own
# price-transparency page.
PROVIDER_USERNAME = "RamiLevi"
PROVIDER_PASSWORD = ""


def get_provider_base_url() -> str:
    """Return the configured Rami Levy provider base URL.

    Overridable via the SMARTCART_RAMI_LEVY_PROVIDER_BASE_URL environment
    variable; defaults to the TLS-valid canonical hostname (see module
    docstring), never to Rami Levy's own currently-broken hostname.
    """
    return os.environ.get(PROVIDER_BASE_URL_ENV_VAR, DEFAULT_PROVIDER_BASE_URL)
