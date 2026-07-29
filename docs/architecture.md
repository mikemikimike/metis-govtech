# METIS Product Suite - Software Architecture & Workspace Specification

## 1. Executive Overview

METIS (Measurement and Evaluation of Trustworthy Intelligent Systems) is an extensible agentic evaluation suite designed for whole-of-government adoption. It enables agency teams to build fast while ensuring AI safety, alignment, and operational reliability by default.

This document outlines the software architecture for the METIS suite. METIS is structured as a **Python Monorepo** managed via **`uv` workspaces**, separating pure domain logic into decoupled packages (`packages/`) and deployable runtimes into application services (`apps/`).

All packages use clean folder paths on disk (`packages/core`, `packages/engine`), while sharing a unified **`metis` Python namespace** (`from metis.core import Trace`, `from metis.engine import Evaluator`). Executable components expose direct CLI commands via `[project.scripts]` entry points.

---

## 2. Technical Stack

* **Workspace & Package Management:** `uv` (Fast Python package resolver and workspace manager)
* **Data Modeling & Validation:** Pydantic v2
* **Namespace Packaging Strategy:** Hatchling (PEP 420 Native Namespaces)
* **CLI Framework:** Typer + Rich (used across `metis-engine`, `metis-wizard`, and `metis-insights`)
* **Database / ORM (Web Backend):** PostgreSQL + SQLAlchemy v2 (Async) + Alembic
* **Task Queue / Worker (Async Processing):** Celery or ARQ + Redis
* **API Framework:** FastAPI

---

## 3. Directory Layout (Clean Folders + Namespace Imports)

Directory names on disk are kept short (`packages/core`), while code inside uses the nested namespace layout (`src/metis/core`).

```text
metis/
├── pyproject.toml                  # Workspace definition and shared settings
├── metis_cli.py                    # Unified CLI entry point (composes sub-package CLIs)
├── uv.lock                         # Unified lockfile for all packages & apps
├── README.md
│
├── packages/                       # Reusable Python packages (Libraries)
│   ├── core/                       # Pydantic models, interfaces, enums, exceptions
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── metis/
│   │           └── core/
│   │
│   ├── metrics/                    # Metric definitions, registry, built-in implementations
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── metis/
│   │           └── metrics/
│   │
│   ├── engine/                     # Trace parsers, evaluation runtime
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── metis/
│   │           └── engine/
│   │               └── cli.py      # CLI entry point (metis-engine)
│   │
│   ├── wizard/                     # Test-suite generators, guardrail wizards, CLI helpers
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── metis/
│   │           └── wizard/
│   │               └── cli.py      # CLI entry point (metis-wizard)
│   │
│   └── insights/                   # Data aggregation, reporting calculations, analytics
│       ├── pyproject.toml
│       └── src/
│           └── metis/
│               └── insights/
│                   └── cli.py      # CLI entry point (metis-insights)
│
├── apps/                           # Runnable web services & execution runtimes
│   ├── api/                        # FastAPI REST service
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── metis/
│   │           └── api/
│   │               └── main.py
│   │
│   └── worker/                     # Asynchronous Celery task processing node
│       ├── pyproject.toml
│       └── src/
│           └── metis/
│               └── worker/
│                   └── tasks.py
│
└── infra/                          # Docker Compose, Kubernetes, and deployment assets
```

---

## 4. Architectural Boundaries & Component Roles

### 4.1. `packages/core` (`metis-core`)
* **Import Path:** `from metis.core import Trace, Score, BaseMetric, MetricRegistry, ExperimentConfig`
* **Purpose:** Single source of truth for standard domain objects, contracts, and infrastructure.
* **Dependencies:** Pure Python + Pydantic v2 only. **Zero external runtime dependencies**.
* **Key Responsibilities:**
  * Schema definitions: `Trace`, `Span`, `Step`, `ToolCall`, `Score`, `AssertionResult`, `EvaluationReport`.
  * Configuration schema: `ExperimentConfig`, `MetricConfig`, `DataSourceConfig` — the contract between wizard (produces) and engine (consumes).
  * Enums: `EvaluationCategory`, `StepType`, `Status`, `SeverityLevel`.
  * Abstract base interfaces: `BaseMetric`, `BaseTraceIngester`, `BaseEvaluator`.
  * Infrastructure: `MetricRegistry` — central lookup for metric implementations by name.
  * Plugin discovery: `discover_ingesters()` / `ingest_trace()` — loads `BaseTraceIngester` implementations via the `metis.trace_ingesters` entry point group.
  * Core exceptions: `TraceParsingError`, `MetricExecutionError`, `InvalidConfigError`.

### 4.2. `packages/metrics` (`metis-metrics`)
* **Import Path:** `from metis.metrics import DEFAULT_REGISTRY, TrajectoryCompleteness`
* **Purpose:** METIS's built-in library of default metric implementations. Third-party teams can write their own metrics using `BaseMetric` from core without depending on this package.
* **Dependencies:** `metis-core` only.
* **Key Responsibilities:**
  * `DEFAULT_REGISTRY`: a pre-populated `MetricRegistry` containing all built-in metrics.
  * Built-in metric implementations (e.g., `TrajectoryCompleteness`, `ToolCallAccuracy`, guardrail pass-rate).
  * Metric authoring utilities (decorators, base helpers) for teams writing custom metrics.

### 4.3. `packages/engine` (`metis-engine`)
* **Import Path:** `from metis.engine import Evaluator`
* **CLI Command:** `uv run metis-engine`
* **Purpose:** Standalone execution engine for running evaluations against traces. Can be imported as a library or executed directly in local terminals and CI/CD pipelines.
* **Dependencies:** `metis-core`, `metis-metrics`, `typer`, `rich`, lightweight HTTP/math/parsing libraries (`httpx`, `numpy`).
* **Key Responsibilities:**
  * Ships built-in trace ingesters (Langfuse, OpenTelemetry) registered via `[project.entry-points."metis.trace_ingesters"]`.
  * CLI commands to evaluate trace files directly (`metis-engine run --trace-file trace.json`).
  * Loads metrics from the registry and executes them against normalized traces.
* **Adding New Trace Formats:** Implement `BaseTraceIngester` from core, then register via entry point in your package's `pyproject.toml`:
  ```toml
  [project.entry-points."metis.trace_ingesters"]
  my_format = "my_package.ingester:MyIngester"
  ```

### 4.4. `packages/wizard` (`metis-wizard`)
* **Import Path:** `from metis.wizard import ConfigGenerator`
* **CLI Command:** `uv run metis-wizard`
* **Purpose:** Interactive wizard and configuration generator for creating evaluation suites and guardrails.
* **Dependencies:** `metis-core`, `metis-metrics`, `typer`, `rich`.
* **Key Responsibilities:**
  * Interactive CLI terminal UI for generating valid suite configuration YAML files.
  * CLI command: `metis-wizard init` to interactively generate evaluation configs.
  * Template generation for custom metric authors.

### 4.5. `packages/insights` (`metis-insights`)
* **Import Path:** `from metis.insights import AnalyticsEngine`
* **CLI Command:** `uv run metis-insights`
* **Purpose:** Analytics computation and reporting engine for evaluation outputs.
* **Dependencies:** `metis-core`, `typer`, `rich`, `pandas`, plotting/summary engines.
* **Key Responsibilities:**
  * Consumes `EvaluationReport` (from `metis.core`) — does NOT depend on engine.
  * Terminal-based analytics rendering (ASCII tables, pass/fail summaries) for developer runs.
  * CLI command: `metis-insights report --results-file results.json`.
  * Programmatic reporting calculations for the API backend.

### 4.6. `packages/testbed` (`metis-testbed`) *(Deferred — Phase 3)*
* **Import Path:** `from metis.testbed import Sandbox`
* **Purpose:** Evaluator calibration and sandbox environment for running agents against controlled scenarios.
* **Dependencies:** `metis-core`, `metis-engine`.
* **Key Responsibilities:**
  * Provides controlled execution environments for agent calibration.
  * Scenario definitions for known-good/known-bad agent trajectories.
  * Calibration utilities for tuning metric thresholds.

> **Note:** Testbed is deferred to Phase 3 (Generalized METIS). The MVP focuses on
> evaluating pre-recorded traces from Langfuse; live sandbox execution comes later.

### 4.7. `apps/api` & `apps/worker` *(Deferred — Phase 4)*
* **Purpose:** The multi-tenant, hosted web platform backend.
* **Dependencies:** All internal `packages/*`, `fastapi`, `sqlalchemy`, `alembic`, `celery`/`redis`.
* **Key Responsibilities:**
  * `apps/api`: Exposes REST endpoints for configuration, trace submission, and fetching insights reports.
  * `apps/worker`: Imports `metis.engine` inside async Celery tasks to process deep trace evaluation jobs off the main HTTP thread.
  * SQLAlchemy ORM: Persists historical runs, scores, and workspace metadata to PostgreSQL.

> **Note:** The web platform is deferred to Phase 4 (Expansion). The MVP and Phase 3
> deliverables are CLI-first: `metis-engine`, `metis-wizard`, and `metis-insights`
> operate as standalone commands. The `apps/` directory structure is reserved but not
> implemented until the product requires a hosted multi-tenant service.

---

## 5. Dependency Rules (DAG)

To prevent circular dependencies, dependencies must flow **downward only**:

```text
         [ apps/api ]       [ apps/worker ]
              │                    │
              └─────────┬──────────┘
                        ▼
              [ packages/engine ]
                   │         │
                   │         ▼
                   │   [ packages/insights ]
                   │
                   ▼
            [ packages/metrics ] ◄── [ packages/wizard ]
                   │
                   ▼
            [ packages/core ]   (Base - Zero local dependencies)
```

> **Key rule:** `wizard` and `insights` do NOT depend on `engine`. Wizard depends on
> `core` + `metrics` (to enumerate available metrics). Insights depends on `core`
> (to read evaluation result types). Only `engine` pulls everything together at runtime.

---

## 6. Implementation Blueprint for Coding Agent

### Step 1: Root Workspace Initialization
Root `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metis"
version = "0.1.0"
description = "Measurement and Evaluation of Trustworthy Intelligent Systems"
requires-python = ">=3.11"
dependencies = [
    "metis-core",
    "metis-engine",
    "metis-metrics",
    "metis-wizard",
    "metis-insights",
]

[project.scripts]
metis = "metis_cli:app"

[tool.hatch.build.targets.wheel]
packages = ["."]
only-include = ["metis_cli.py"]

[tool.uv]
package = true

[tool.uv.sources]
metis-core = { workspace = true }
metis-engine = { workspace = true }
metis-metrics = { workspace = true }
metis-wizard = { workspace = true }
metis-insights = { workspace = true }

[tool.uv.workspace]
members = [
    "packages/*",
    "apps/*",
]
```

> **Note:** The root project must explicitly depend on workspace members for `uv sync` to install them into the virtualenv. Without these dependencies, workspace members are resolved but not installed.
>
> The root also requires `build-system`, `tool.uv.package = true`, and `tool.hatch.build.targets.wheel` to install its own `[project.scripts]` entry point (the unified `metis` CLI).

### Step 2: Core Package Configuration (`packages/core/pyproject.toml`)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metis-core"
version = "0.1.0"
description = "Core data models and abstractions for the METIS suite"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/metis"]
```

### Step 3: Engine Package Configuration (`packages/engine/pyproject.toml`)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metis-engine"
version = "0.1.0"
description = "Evaluation engine and trace parser for METIS"
requires-python = ">=3.11"
dependencies = [
    "metis-core",
    "typer>=0.9.0",
    "rich>=13.0.0",
    "httpx>=0.25.0",
]

[project.scripts]
metis-engine = "metis.engine.cli:app"

[tool.uv.sources]
metis-core = { workspace = true }

[tool.hatch.build.targets.wheel]
packages = ["src/metis"]
```

### Step 4: Wizard Package Configuration (`packages/wizard/pyproject.toml`)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metis-wizard"
version = "0.1.0"
description = "Interactive evaluation setup wizard and CLI generator"
requires-python = ">=3.11"
dependencies = [
    "metis-core",
    "metis-metrics",
    "typer>=0.9.0",
    "rich>=13.0.0",
]

[project.scripts]
metis-wizard = "metis.wizard.cli:app"

[tool.uv.sources]
metis-core = { workspace = true }
metis-metrics = { workspace = true }

[tool.hatch.build.targets.wheel]
packages = ["src/metis"]
```

### Step 5: Insights Package Configuration (`packages/insights/pyproject.toml`)
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "metis-insights"
version = "0.1.0"
description = "Analytics and visualization engine for evaluation reports"
requires-python = ">=3.11"
dependencies = [
    "metis-core",
    "typer>=0.9.0",
    "rich>=13.0.0",
    "pandas>=2.0.0",
]

[project.scripts]
metis-insights = "metis.insights.cli:app"

[tool.uv.sources]
metis-core = { workspace = true }

[tool.hatch.build.targets.wheel]
packages = ["src/metis"]
```

---

## 7. Developer Execution Workflow

### Initial Repository Bootstrap Script
To initialize the workspace and set up all clean folder structures in one command:

```bash
uv init metis && cd metis && \
for pkg in core engine wizard insights; do mkdir -p packages/$pkg/src/metis/$pkg && touch packages/$pkg/src/metis/$pkg/__init__.py; done && \
for app in api worker; do mkdir -p apps/$app/src/metis/$app && touch apps/$app/src/metis/$app/__init__.py; done
```

### CLI Command Invocation

The primary CLI is the unified `metis` command, which composes all sub-package CLIs:

```bash
# Unified CLI (preferred)
uv run metis wizard init
uv run metis engine run --trace-file ./tests/fixtures/langfuse_trace.json
uv run metis insights report --results-file ./results.json

# Version info
uv run metis engine -V
```

Per-package standalone commands are also available (useful for CI or isolated installs):

```bash
uv run metis-wizard init
uv run metis-engine run --trace-file ./tests/fixtures/langfuse_trace.json
uv run metis-insights report --results-file ./results.json
```

---

## 8. Testing Strategy

### Directory Layout
```text
tests/
├── unit/                       # Per-package unit tests (mirror package structure)
│   ├── core/
│   ├── metrics/
│   ├── engine/
│   ├── wizard/
│   └── insights/
├── integration/                # Cross-package integration tests
└── fixtures/                   # Shared test data (trace files, configs)
    ├── langfuse_trace.json
    └── experiment.yaml
```

### Conventions
* **Unit tests** (`tests/unit/<package>/`) test a single package in isolation. Mock external dependencies.
* **Integration tests** (`tests/integration/`) verify cross-package flows (e.g., ingesting a trace file through the engine and producing a report).
* **Fixtures** (`tests/fixtures/`) hold sample trace files and experiment configs shared across test suites.
* Run all tests: `uv run pytest`
* Run a single package's tests: `uv run pytest tests/unit/engine/`

---

## 9. Makefile (Developer Task Runner)

A root `Makefile` provides a uniform interface for common development tasks across the monorepo. Developers and CI pipelines use `make <target>` instead of remembering individual `uv run` incantations.

### Target Reference

```makefile
.PHONY: help install clean lint lint-fix format format-check fix typecheck test check ci

help:
	@printf "Available targets:\n"
	@printf "  make install             Install all workspace dependencies\n"
	@printf "  make lint                Run Ruff lint checks\n"
	@printf "  make lint-fix            Apply Ruff lint autofixes\n"
	@printf "  make format              Format Python files with Ruff\n"
	@printf "  make format-check        Check formatting without changes\n"
	@printf "  make fix                 Apply lint autofixes and formatting\n"
	@printf "  make typecheck           Run Pyright type checking\n"
	@printf "  make test                Run full test suite with pytest\n"
	@printf "  make test-unit           Run unit tests only\n"
	@printf "  make test-integration    Run integration tests only\n"
	@printf "  make check               Run lint, format, and type checks\n"
	@printf "  make ci                  Run the full CI suite (check + test)\n"
	@printf "  make clean               Remove generated/cached files\n"

install:
	uv sync --group dev

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format . --check

fix:
	$(MAKE) lint-fix
	$(MAKE) format

typecheck:
	uv run pyright

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit/

test-integration:
	uv run pytest tests/integration/

check:
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) typecheck

ci:
	$(MAKE) check
	$(MAKE) test

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache .pyright
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv
```

### Design Principles

* **Single entry point:** All targets operate from the workspace root. `uv` resolves workspace members automatically — no per-package `cd` required.
* **Composable targets:** `check` = `lint` + `format-check` + `typecheck`. `ci` = `check` + `test`. Developers can run any subset.
* **CI parity:** The `ci` target mirrors what CI pipelines execute. Running `make ci` locally catches failures before push.
* **Recursive cleanup:** `clean` removes caches across the entire monorepo tree, not just the root.

### Per-Package Testing

For focused development on a single package, bypass the Makefile and run pytest directly:

```bash
uv run pytest tests/unit/core/
uv run pytest tests/unit/engine/
```

The Makefile's `test` target always runs the full suite — this is intentional to prevent partial-test CI drift.

---

## 10. Next Steps for Coding Agent

1. Execute the initial workspace bootstrap shell command from Section 7.
2. Populate `pyproject.toml` files for all sub-packages using the Hatchling configuration blueprints in Section 6.
3. Wire package CLI entry points (`[project.scripts]`) using Typer in `src/metis/*/cli.py`.
4. Implement `metis.core` Pydantic models (`Trace`, `Span`, `Score`, `AssertionResult`) and interfaces.
5. Build `metis.engine` Langfuse trace parser and basic CLI evaluation execution logic (`uv run metis-engine`).
6. Run `uv sync` and verify imports work cleanly via `from metis.core import Trace`.
7. Create the root `Makefile` using the blueprint in Section 9. Verify `make ci` passes.

---

## 11. Agent Instructions (`AGENTS.md`) Strategy

Agent instruction files follow the directory hierarchy — agents pick up all `AGENTS.md` files from the repo root down to the directory they're working in.

### Root (`AGENTS.md`)
Repo-wide conventions shared across all packages and apps:

- Python version requirement (>=3.11), uv workspace setup
- How to run tests (`uv run pytest`, per-package: `uv run pytest tests/unit/<pkg>/`)
- Linting/formatting rules, naming conventions
- Dependency DAG rules (Section 5) — packages must not introduce upward dependencies
- Namespace packaging convention (`src/metis/<pkg>/`)
- PR/commit conventions, CI notes

### Per-Package (`packages/<pkg>/AGENTS.md`)
Context specific to a single library package:

- Package purpose and key abstractions (e.g., `packages/core`: "Pure domain models, zero external deps beyond Pydantic")
- Domain-specific terminology and invariants
- Testing patterns unique to that package
- Dependency constraints (what this package may and may not import)

### Per-App (`apps/<app>/AGENTS.md`)
Deployment and runtime context for runnable services:

- How to run locally, required env vars and infrastructure (e.g., Redis, PostgreSQL)
- API design conventions, auth patterns
- Dockerfile / container notes

### When to Add Per-Directory Files
A single root `AGENTS.md` is sufficient while packages are small. Add per-package files when:

- A package has domain-specific terminology an agent consistently misunderstands
- Testing or running a package requires non-obvious setup (external services, fixtures)
- Dependency constraints need reinforcing (e.g., "this package must remain pure Python")
