# 0005. Dependency licensing policy

## Status

Accepted

## Context

SmartCart is commercial software. Open-source dependencies carry a range of
licenses, and not all of them are straightforwardly compatible with use in
a proprietary commercial product (for example, strong copyleft licenses can
impose obligations on the software that links against them). Adding
dependencies without checking their license first risks discovering a
conflict only after the dependency is deeply embedded in the codebase.

## Decision

Before introducing any meaningful new dependency (a runtime dependency, or
a development dependency that gets embedded/redistributed), its license
must be identified and reviewed for compatibility with commercial,
proprietary use.

- Permissive licenses (e.g. MIT, BSD, Apache 2.0) are generally low-risk for
  this project's use case.
- Copyleft or otherwise ambiguous licenses require explicit discussion and
  sign-off before adoption, and should be flagged rather than added
  silently.
- If a dependency's license is uncertain or cannot be readily determined,
  work must stop and the question must be raised rather than guessing or
  proceeding anyway.

This policy applies to direct dependencies added intentionally. It does not
require re-auditing the entire transitive dependency tree by hand for every
change, but a dependency with an unusual or copyleft license should be
noticed and raised at the point it is introduced.

This ADR is an engineering process policy, not legal advice. It does not
substitute for a legal/licensing review by qualified counsel before the
product ships commercially; it exists to avoid casually accumulating
licensing risk during development in the meantime.

## Consequences

- Adding a dependency takes slightly longer, since its license must be
  checked first.
- Development tooling for Phase 0 (pytest, pytest-cov, mypy, ruff,
  pre-commit) was selected as widely-used, permissively-licensed (MIT/
  Apache-2.0/MPL-2.0 family) tooling consistent with this policy.
- Any future dependency addition should note, at minimum, its license in
  the PR/commit description introducing it.
