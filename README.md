# SmartCart (working title)

> The product name is not final.

SmartCart is a commercial grocery shopping platform for the Israeli market.
The goal is to help households decide where and when to shop based on their
shopping list, current supermarket prices, product availability, store
location, and travel/detour time — with the household making the final
tradeoff between price, missing items, and travel time, rather than that
tradeoff being hidden behind an opaque score.

The initial user-facing interface is expected to be WhatsApp, but the
shopping engine itself is being built channel-independent (see
[`docs/adr/0002-channel-independent-core.md`](docs/adr/0002-channel-independent-core.md))
so it can later be reused by other clients.

## Current phase

**Phase 0 — engineering foundation.**

This repository currently contains only project scaffolding: tooling,
configuration, CI, and architecture decision records. There is no
supermarket/domain implementation yet — no collectors, parsers, database,
product matching, routing, AI integration, or WhatsApp integration. See
[`docs/adr/`](docs/adr/) for the architectural decisions made so far.

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
