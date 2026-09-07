# 0003. No third-party supermarket scraper/parser code

## Status

Accepted

## Context

Large Israeli supermarket chains are required, under Israeli price
transparency regulation, to publish price, store, and promotion data
publicly. Third-party open-source projects already exist that scrape and
parse this data for various Israeli supermarket chains, and have already
been informally investigated as part of scoping this product.

SmartCart is a commercial product. Using implementation code from
third-party repositories of unknown or incompatible license, or code that
was itself derived from such repositories, would create meaningful legal
and commercial risk: license incompatibility, provenance disputes, or
inadvertently encoding another project's assumptions or bugs into a
production system without understanding them.

## Decision

SmartCart's collectors and parsers for supermarket data must be
independently implemented, working only from:

- The official/public data sources themselves (the published price/store/
  promotion files or endpoints), and
- Publicly available specifications or documentation describing their
  format, where such specifications exist.

Contributors and any automated coding assistance (including AI tools used
during development) must not inspect, copy, translate, port, rewrite,
adapt, or otherwise derive implementation code from third-party Israeli
supermarket scraper/parser repositories. This includes reading such
repositories "for reference" and then reproducing their approach or
structure from memory.

Such repositories must not be added as dependencies of this project unless
that decision is explicitly approved later, after a licensing and legal
review.

This restriction applies specifically to implementation code for
collecting/parsing supermarket data. It does not restrict use of the
published official data itself (which is the intended primary data
source), nor does it restrict ordinary use of unrelated, properly licensed
open-source libraries elsewhere in the project.

## Consequences

- Building each supermarket collector/parser from scratch is expected to
  take longer than adapting an existing implementation would.
- Some rediscovery of already-solved problems (e.g. quirks in a specific
  chain's published file format) is an accepted cost of this policy.
- Code review for any new collector/parser should be able to point to the
  official source or specification the implementation was derived from.
- If a specification is ambiguous or a source's behavior is unclear, the
  correct response is to inspect the actual published data/output and
  write tests against it, not to consult a third-party implementation.
