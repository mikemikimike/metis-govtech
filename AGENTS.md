# METIS — Codebase Guide

## Overview

METIS (Measurement and Evaluation of Trustworthy Intelligent Systems) is a Python monorepo providing an extensible agentic evaluation suite. It ingests agent execution traces and runs configurable metrics to produce safety/alignment diagnostics.

## Tech Stack

- **Language:** Python ≥ 3.11
- **Workspace/Package Manager:** uv (single lockfile at root)
- **Build Backend:** Hatchling + hatch-vcs (version from git tags)
- **Data Modeling:** Pydantic v2
- **CLI Framework:** Typer + Rich
- **Linting/Formatting:** Ruff
- **Type Checking:** Pyright
- **Testing:** pytest
- **Dev Environment:** direnv (`.envrc` auto-activates venv)

## Commands

```bash
make install        # uv sync --group dev
make check          # lint + format-check + typecheck (non-mutating)
make fix            # auto-fix lint + format
make ci             # full CI suite (check + test)
make clean          # remove generated/cached files
```

Individual targets: `lint`, `lint-fix`, `format`, `format-check`, `typecheck`.

Test targets are scaffolded but currently commented out: `test`, `test-unit`, `test-integration`.

## Project Layout

```
metis/
├── pyproject.toml          # Workspace root (lists all members)
├── metis_cli.py            # Unified CLI entry point (composes sub-CLIs)
├── uv.lock                 # Single lockfile
├── Makefile                # Dev/CI interface
├── packages/
│   ├── core/               # metis-core — domain schemas, interfaces, registry
│   ├── metrics/            # metis-metrics — shared metric catalog
│   ├── engine/             # metis-engine — evaluation runtime + trace ingesters
│   └── wizard/             # metis-wizard — interactive config generator
├── apps/
│   ├── api/                # REST backend (Stage 3 — deferred)
│   └── web/                # React frontend (Stage 3 — deferred)
└── docs/
    └── architecture.md     # Normative architectural specification
```

Each package lives under `packages/<name>/src/metis/<name>/` using PEP 420 namespace packages.

## Dependency DAG (downward only)

```
engine ──► metrics ──► core
wizard ──► metrics ──► core
insights ──────────────► core
```

Key invariants:
- `core` has zero workspace dependencies (only Pydantic + stdlib)
- `metrics` depends only on `core`
- `wizard` and `engine` depend on `core` + `metrics` but NOT on each other
- `insights` depends only on `core`

## Architecture

- **metis-core:** Domain schemas (Trace, Span, Score, etc.), abstract interfaces (BaseMetric, BaseTraceIngester), MetricRegistry, plugin discovery via entry points.
- **metis-metrics:** Pre-populated DEFAULT_REGISTRY with built-in evaluators; metric authoring utilities.
- **metis-engine:** Evaluation runtime — ingests traces (Langfuse, OTEL), executes metrics from registry. CLI: `metis engine run --trace-file <path>`.
- **metis-wizard:** Interactive CLI for generating evaluation config YAML. CLI: `metis wizard init`.

## Coding Conventions

- Namespace imports: `from metis.core import ...`, `from metis.engine import ...`
- All shared domain objects use Pydantic v2 models
- CLIs use Typer with sub-app composition (see `metis_cli.py`)
- Versioning: unified across all packages via `hatch-vcs` (git tags `v*`)
- No static `version` fields — always `dynamic = ["version"]`

## Current Stage

**Stage 1 (MVP):** `core`, `metrics`, `engine` — CLI evaluation of pre-recorded traces. Active development.

See `docs/architecture.md` for the full normative specification.
