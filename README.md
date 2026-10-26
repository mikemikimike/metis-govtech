<p align="center">
  <img src="docs/assets/METIS.png" alt="METIS" width="160">
</p>

<h1 align="center">METIS</h1>

<p align="center">
  <strong>Measurement and Evaluation of Trustworthy Intelligent Systems</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%E2%89%A53.11-3776AB?logo=python&logoColor=white" alt="Python 3.11 or later">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-4c1" alt="MIT licence"></a>
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="Status: active">
</p>

<p align="center">
  METIS is an extensible agentic evaluation suite for assessing AI safety, alignment, and operational reliability. It ingests agent execution traces (from platforms like Langfuse and OpenTelemetry), runs configurable evaluation metrics against them, and produces diagnostics and compliance analytics.
</p>

## Table of Contents

- [Status](#status)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Development](#development)
- [Project Layout](#project-layout)
- [Versioning](#versioning)
- [Maintainers and contact](#maintainers-and-contact)
- [Security](#security)
- [License](#license)

## Status

**Active.** METIS is under active development. We monitor issues and pull requests.
The current release is a pre-release, so the API can change.

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
| [**metis-insights**](packages/insights/) | Report generation from evaluation results |
| [**metis-testbed**](packages/testbed/) | Human-reviewed Wizard evaluation cases and reference Specifications |

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

See the user guides for usage instructions:

- [`docs/guide/engine.md`](docs/guide/engine.md) — evaluation engine (package details in
  [`packages/engine/README.md`](packages/engine/README.md))
- [`docs/guide/wizard.md`](docs/guide/wizard.md) — Wizard CLI, web, and API
- [`docs/guide/insights.md`](docs/guide/insights.md) — `metis insights report`, which builds the report from evaluation results
- [`docs/guide/models.md`](docs/guide/models.md) — the model and gateway of each LLM role, and the
  one `.env` file that every command reads

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.

```bash
make check          # lint + format-check + typecheck (non-mutating)
make fix            # auto-fix lint issues and format code
make ci             # full CI suite
make clean          # remove generated/cached files
```

## Logging & Console Output

All packages use centralized logging and console output from `metis-core`:

```python
from metis.core.logging import get_logger
from metis.core.console import console

# Operational logging (stderr) — for developers and CI
log = get_logger()
log.info("evaluation_started", trace_id="abc-123", metrics_count=5)

# User-facing output (stdout) — for end users
console.print("[bold]Results:[/bold] 4 passed, 1 failed")
```

Verbosity is controlled via CLI flags:

```bash
metis engine simulate --input-dir ./exp       # simulation only; writes run records
metis engine evaluate --experiment-dir ./experiments/exp-20260820-143000  # score the output that simulate wrote
metis engine run --input-dir ./exp            # simulation + evaluation + report
metis engine run --input-dir ./exp -v         # INFO: operational progress
metis engine run --input-dir ./exp -vv        # DEBUG: full diagnostics
```

Simulation uses the live TUI in a terminal. Evaluation uses a normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file.

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
│   ├── wizard/             # metis-wizard
│   ├── insights/           # metis-insights
│   └── testbed/            # metis-testbed
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

## Maintainers and contact

METIS is maintained by [@mqf20](https://github.com/mqf20) and
[@leannetan](https://github.com/leannetan). For questions, contact
[aipractice@tech.gov.sg](mailto:aipractice@tech.gov.sg).

## Security

Do not report security vulnerabilities in public issues. See [SECURITY.md](SECURITY.md)
for how to report a vulnerability.

## License

METIS is released under the [MIT License](LICENSE).
