<p align="center">
  <img src="docs/assets/METIS.png" alt="METIS" width="128">
</p>

# METIS

**Measurement and Evaluation of Trustworthy Intelligent Systems**

METIS is an extensible agentic evaluation suite for assessing AI safety, alignment, and operational reliability. It ingests agent execution traces (from platforms like Langfuse and OpenTelemetry), runs configurable evaluation metrics against them, and produces diagnostics and compliance analytics.

## Table of Contents

- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Development](#development)
- [Project Layout](#project-layout)
- [Versioning](#versioning)

## Architecture

```
                        ┌─────────────┐
                        │  METIS-web  │
                        └──────┬──────┘
                               │ HTTP
                        ┌──────▼──────┐
                        │  METIS-api  │
                        └──────┬──────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
┌──────▼──────┐   ┌───────────▼───────────┐   ┌──────▼──────┐
│ METIS-wizard│   │     METIS-engine      │   │METIS-insights│
│  Config Gen │   │  Evaluation Runtime   │   │  Analytics   │
└──────┬──────┘   └───────────────────────┘   └──────┬──────┘
       │                       │                     │
       │               ┌──────▼──────┐               │
       └──────────────►│METIS-library │◄─────────────┘
                       │   Catalog    │
                       └──────┬──────┘
                              │
                       ┌──────▼──────┐
                       │  METIS-core │
                       │Domain Schemas│
                       └─────────────┘
```

| Package | Description |
|---------|-------------|
| [**metis-core**](packages/core/) | Domain schemas and standard interfaces |
| [**metis-library**](packages/library/) | Shared catalog — metrics, skills, and reusable components |
| [**metis-engine**](packages/engine/) | Evaluation runtime; ingests traces and executes metrics |
| [**metis-wizard**](packages/wizard/) | Interactive evaluation config generator |
| [**metis-insights**](packages/insights/) | Trajectory diagnostics and compliance analytics |

For the full specification see [docs/architecture.md](docs/architecture.md).

## Quickstart

### Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (workspace and package manager)

### Install

```bash
make install
```

### Usage

See individual package READMEs for usage instructions:

- [`packages/engine/README.md`](packages/engine/README.md) — evaluation engine
- [`packages/wizard/README.md`](packages/wizard/README.md) — config generator

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.

```bash
make check          # lint + format-check + typecheck (non-mutating)
make fix            # auto-fix lint issues and format code
make ci             # full CI suite
make clean          # remove generated/cached files
```

## Project Layout

```
metis/
├── pyproject.toml          # Workspace root
├── metis_cli.py            # Unified CLI entry point
├── uv.lock                 # Single lockfile
├── packages/
│   ├── core/               # metis-core
│   ├── library/            # metis-library
│   ├── engine/             # metis-engine
│   └── wizard/             # metis-wizard
├── apps/
│   ├── api/                # REST backend
│   └── web/                # React frontend
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── docs/
```

## Versioning

Each package maintains its own **independent semantic version**. Releases are tracked with scoped git tags (`<package-name>/v<semver>`). Every merge to `main` that modifies package source MUST be tagged with a version bump for the affected package(s).

See [CONTRIBUTING.md](CONTRIBUTING.md#versioning--release) for the full release flow and tagging conventions, and [docs/architecture.md](docs/architecture.md) for the versioning specification.
