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
       └──────────────►│ METIS-metrics│◄─────────────┘
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
| [**metis-metrics**](packages/metrics/) | Shared metric catalog — built-in evaluators and authoring utilities |
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

```bash
metis wizard init                            # generate an evaluation config
metis engine run --trace-file trace.json     # run evaluations
metis insights report --results-file out.json # view results
```

Each sub-command is also available as a standalone CLI (`metis-engine`, `metis-wizard`, `metis-insights`).

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
│   ├── metrics/            # metis-metrics
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

See [docs/architecture.md](docs/architecture.md) for the full versioning specification.
