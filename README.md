# SmartCart (working title)

> The product name is not final.

SmartCart is a commercial grocery shopping platform for the Israeli market.
The goal is to help households decide where and when to shop based on their
shopping list, current supermarket prices, product availability, store
location, and travel/detour time — with the household making the final
tradeoff between price, missing items, and travel time, rather than that
tradeoff being hidden behind an opaque score.

The owner-confirmed direction for the user-facing product is a primary
Android/iOS application, with a complementary WhatsApp bot running in
parallel (see [`docs/project-status.md`](docs/project-status.md) — this is
relayed direction, not implemented code, and no framework choice is
implied). The shopping engine itself is being built channel-independent
(see [`docs/adr/0002-channel-independent-core.md`](docs/adr/0002-channel-independent-core.md))
so it can later be reused by whichever clients are eventually built.

## Documentation map

- [`docs/project-status.md`](docs/project-status.md) — current
  implementation snapshot, owner-confirmed direction, and open questions.
- [`docs/development-workflow.md`](docs/development-workflow.md) — the
  agreed process: task agreement, implementation stages, and review/
  commit/push gates.
- [`docs/work-log.md`](docs/work-log.md) — chronological, stage-by-stage
  history of instructions, decisions, changes, and checks.
- [`docs/adr/`](docs/adr/) — architecture decision records.
- [`CLAUDE.md`](CLAUDE.md) — continuity instructions for Claude Code
  sessions working in this repository.

## Current state

This repository is well past scaffolding-only: it contains working
per-retailer collectors, a normalization layer, and two persistence-related
spikes (see [`docs/project-status.md`](docs/project-status.md) for the full
component-by-component snapshot with file references). The distinctions
below are easy to blur from a summary alone, so they are stated explicitly:

- **Collector, normalize, and persistence components exist and are
  individually tested, but nothing in `src/` wires them into a runnable
  application.** There is no CLI or script entry point anywhere in
  `src/smartcart` (no `argparse`, `click`, `sys.argv`, or `if __name__`).
  `src/smartcart/integration/occurrence_activation.py` is the only module
  that bridges normalized data into persistence, and its only caller found
  repository-wide is its own test.
- **No complete collector → actual normalization → persistence test path
  was found in the inspection performed. Indirect paths through
  helpers/fixtures remain unverified; the originally approved scope of
  such coverage also remains unverified. Existing DB tests are present.**
  (This supersedes the stronger absence claims previously stated here and
  in `docs/work-log.md` WL-0002; see WL-0009, WL-0016, and WL-0019.) The
  inspected test files exercise these three connections separately: (1)
  real collector fetch → Round 1 raw
  persistence (`tests/db_spike/test_real_output_acceptance.py`, gated
  behind a live-network env var. Not executed during this documentation
  checkpoint; prior execution history was not verified. It does not use
  `normalize` at all); (2) a collector-record-shaped input →
  a `normalize` function (`tests/normalize/test_shufersal_normalize.py`,
  `test_rami_levy_normalize.py`, `test_rami_levy_standard_normalize.py`),
  using locally constructed raw records, not literal collector output; and
  (3) a synthetically constructed `NormalizedPriceItem` →
  `activate_normalized_occurrence` → Round 2 persistence
  (`tests/db_spike/test_normalized_occurrence_activation.py`), never
  calling an actual `normalize` function. No test file anywhere imports
  both a real `normalize.*` transformation function and
  `smartcart.integration.occurrence_activation`.
- **Promotions normalization is implemented; Promotions XML parsing,
  persistence, and basket/shopping-list functionality are not.** The
  normalized Promotions contract (`src/smartcart/normalize/promotion.py`)
  is implemented and tested against an internal, explicitly provisional
  raw shape — not a real retailer XML parser — and has no persistence path.
- **`db_spike/` and `durability_spike/` are documented
  correctness-of-mechanism spikes, not production infrastructure.** Both
  say so directly in their own module docstrings and in ADR 0009/ADR 0010.
  Neither the name nor the presence of tests implies production readiness.
- **CI configuration existing is not the same claim as CI currently
  passing.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs
  `ruff check`, `ruff format --check`, `mypy`, and `pytest --cov`; treat
  "configured" and "currently green" as separate facts until a run is
  actually recorded (see [`docs/work-log.md`](docs/work-log.md)).
- **The Android/iOS app and WhatsApp bot are an owner-confirmed direction,
  not implemented code.** See [`docs/project-status.md`](docs/project-status.md).

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) for environment and dependency management

## Setup

```sh
uv sync
```

This creates a `.venv` and installs the project's development dependencies
(`pytest`, `pytest-cov`, `mypy`, `ruff`, `pre-commit`).

Optionally, install the pre-commit hooks:

```sh
uv run pre-commit install
```

Copy `.env.example` to `.env` if/when local configuration is needed (no
secrets are required at this phase).

## Running tests

```sh
uv run pytest
```

## Linting and formatting

```sh
uv run ruff check .
uv run ruff format --check .
```

## Type checking

```sh
uv run mypy
```
