# METIS — Codebase Guide

## Overview

METIS (Measurement and Evaluation of Trustworthy Intelligent Systems) is a Python monorepo providing an extensible agentic evaluation suite. It ingests agent execution traces and runs configurable metrics to produce safety/alignment diagnostics.

## Tech Stack

- **Language:** Python ≥ 3.11
- **Workspace/Package Manager:** uv (single lockfile at root)
- **Build Backend:** Hatchling (static version in each package's `pyproject.toml`)
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
│   ├── library/            # metis-library — shared catalog (metrics, skills, etc.)
│   ├── engine/             # metis-engine — evaluation runtime + trace ingesters
│   └── wizard/             # metis-wizard — interactive config generator
├── apps/
│   ├── api/                # REST backend
│   └── web/                # React frontend
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── docs/
    └── architecture.md     # Normative architectural specification
```

Each package lives under `packages/<name>/src/metis/<name>/` using PEP 420 namespace packages.

## Dependency DAG (downward only)

```
engine ──► library ──► core
wizard ──► library ──► core
insights ───────────────► core
```

Key invariants:
- `core` has zero workspace dependencies (only Pydantic + stdlib)
- `library` depends only on `core`
- `wizard` and `engine` depend on `core` + `library` but NOT on each other
- `insights` depends only on `core`

## Architecture

- **metis-core:** Domain schemas (Trace, Span, Score, etc.), abstract interfaces (BaseMetric, BaseTraceIngester), MetricRegistry, plugin discovery via entry points.
- **metis-library:** Shared catalog of metrics, skills, and reusable components; referenced by FQN from wizard configs and executed by the engine.
- **metis-engine:** Evaluation runtime — ingests traces (Langfuse, OTEL), executes metrics from registry. CLI: `metis engine run --trace-file <path>`.
- **metis-wizard:** Interactive CLI for generating evaluation config YAML. CLI: `metis wizard init`.
- **metis-insights:** Trajectory diagnostics and compliance analytics. CLI: `metis insights report --results-file <path>`.

## Contributing

All contributors (human and AI) MUST follow the guidelines in [CONTRIBUTING.md](CONTRIBUTING.md). This includes branching conventions, commit message style, testing requirements, dependency DAG invariants, and PR expectations.

## Coding Conventions

- Namespace imports: `from metis.core import ...`, `from metis.engine import ...`
- All shared domain objects use Pydantic v2 models
- CLIs use Typer with sub-app composition (see `metis_cli.py`)
- Versioning: independent per package via static `version` in `pyproject.toml`; scoped git tags `<package-name>/v<semver>`
- Every merge to `main` MUST be tagged with a version bump for the affected package(s)
- Commit messages on `main` MUST be prefixed with package scope (e.g., `engine: fix trace parsing`)

## Per-Package Guides

When working on a specific package, read its local `AGENTS.md` for package-specific instructions:

- [`packages/core/AGENTS.md`](packages/core/AGENTS.md) — metis-core
- [`packages/library/AGENTS.md`](packages/library/AGENTS.md) — metis-library
- [`packages/engine/AGENTS.md`](packages/engine/AGENTS.md) — metis-engine
- [`packages/wizard/AGENTS.md`](packages/wizard/AGENTS.md) — metis-wizard
- [`apps/api/AGENTS.md`](apps/api/AGENTS.md) — metis-api

See `docs/architecture.md` for the full normative specification.
