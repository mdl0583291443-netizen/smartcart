# 0001. Target Python 3.12

## Status

Accepted

## Context

The development machine has several Python interpreters available side by
side: 3.9, 3.10, 3.12, and 3.14. The project needs one pinned target version
for the virtual environment, CI, and type checking, rather than "whatever
happens to be first on PATH."

Two naive choices were both rejected:

- Staying on Python 3.9, the oldest installed interpreter, purely because it
  was already present. Python 3.9 lacks a number of typing and standard
  library improvements (e.g. the `X | Y` union syntax without
  `from __future__ import annotations`, `tomllib`, improved `asyncio` and
  `zoneinfo` ergonomics) that make the strict-typing, tooling-heavy workflow
  this project wants noticeably more pleasant. Python 3.9 also reaches
  end-of-life before this product is expected to be commercially mature,
  which is an unnecessary constraint to accept on day one.
- Jumping straight to Python 3.14, the newest interpreter installed on this
  machine, purely because it is the newest available. A brand-new major
  version has had the least real-world exposure: third-party libraries lag
  in adding support, wheels are more likely to be missing for a given
  platform, and undiscovered interpreter bugs are more likely. For a
  commercial project prioritizing reliability and maintainability, adopting
  the newest interpreter merely because it exists is choosing novelty over
  stability without a corresponding benefit.

## Decision

Target Python 3.12 for development, CI, and type checking.

Python 3.12 is a mature, widely-adopted release: it has broad third-party
library and tooling support, is well past its initial-release stabilization
period, and still has several years of upstream support ahead of it. It also
includes the modern typing features (built-in generic syntax, `X | Y`
unions, improved error messages, and performance improvements over 3.9/3.10)
that the project's strict-mypy, tooling-first approach relies on.

The version is pinned explicitly via `.python-version` and
`requires-python = ">=3.12,<3.13"` in `pyproject.toml`, rather than left
implicit, so that `uv` and CI consistently select the same interpreter
regardless of what else is installed on a given machine.

## Consequences

- Any language or standard-library feature introduced after 3.12 is
  unavailable until this decision is revisited.
- Contributors and CI must have Python 3.12 available (via `uv python
  install 3.12`, which does not require it to be pre-installed).
- Revisiting this decision (e.g. moving to 3.13+) should happen deliberately,
  once the newer version has matured and there is a concrete benefit, not
  automatically when a newer interpreter is released.
