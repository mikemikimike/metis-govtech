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
│   ├── engine/                     # Trace parsers, metrics, evaluation engine
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
* **Import Path:** `from metis.core import Trace, Score, BaseMetric`
* **Purpose:** Single source of truth for standard domain objects and contracts.
* **Dependencies:** Pure Python + Pydantic v2 only. **Zero external runtime dependencies**.
* **Key Responsibilities:**
  * Schema definitions: `Trace`, `Span`, `Step`, `ToolCall`, `Score`, `AssertionResult`, `EvaluationReport`.
  * Enums: `EvaluationCategory`, `StepType`, `Status`, `SeverityLevel`.
  * Abstract base interfaces: `BaseMetric`, `BaseTraceIngester`, `BaseEvaluator`.
  * Core exceptions: `TraceParsingError`, `MetricExecutionError`, `InvalidConfigError`.

### 4.2. `packages/engine` (`metis-engine`)
* **Import Path:** `from metis.engine import Evaluator`
* **CLI Command:** `uv run metis-engine`
* **Purpose:** Standalone execution engine for running evaluations against traces. Can be imported as a library or executed directly in local terminals and CI/CD pipelines.
* **Dependencies:** `metis-core`, `typer`, `rich`, lightweight HTTP/math/parsing libraries (`httpx`, `numpy`).
* **Key Responsibilities:**
  * Ingests raw telemetry (e.g., Langfuse JSON format, OpenTelemetry) and normalizes it to `metis.core.Trace`.
  * CLI commands to evaluate trace files directly (`metis-engine run --trace-file trace.json`).
  * Executes assertion logic, guardrails, and LLM-as-a-judge evaluators.

### 4.3. `packages/wizard` (`metis-wizard`)
* **Import Path:** `from metis.wizard import ConfigGenerator`
* **CLI Command:** `uv run metis-wizard`
* **Purpose:** Interactive wizard and configuration generator for creating evaluation suites and guardrails.
* **Dependencies:** `metis-core`, `metis-engine`, `typer`, `rich`.
* **Key Responsibilities:**
  * Interactive CLI terminal UI for generating valid suite configuration YAML files.
  * CLI command: `metis-wizard init` to interactively generate evaluation configs.
  * Template generation for custom metric authors.

### 4.4. `packages/insights` (`metis-insights`)
* **Import Path:** `from metis.insights import AnalyticsEngine`
* **CLI Command:** `uv run metis-insights`
* **Purpose:** Analytics computation and reporting engine for evaluation outputs.
* **Dependencies:** `metis-core`, `typer`, `rich`, `pandas`, plotting/summary engines.
* **Key Responsibilities:**
  * Terminal-based analytics rendering (ASCII tables, pass/fail summaries) for developer runs.
  * CLI command: `metis-insights report --results-file results.json`.
  * Programmatic reporting calculations for the API backend.

### 4.5. `apps/api` & `apps/worker`
* **Purpose:** The multi-tenant, hosted web platform backend.
* **Dependencies:** All internal `packages/*`, `fastapi`, `sqlalchemy`, `alembic`, `celery`/`redis`.
* **Key Responsibilities:**
  * `apps/api`: Exposes REST endpoints for configuration, trace submission, and fetching insights reports.
  * `apps/worker`: Imports `metis.engine` inside async Celery tasks to process deep trace evaluation jobs off the main HTTP thread.
  * SQLAlchemy ORM: Persists historical runs, scores, and workspace metadata to PostgreSQL.

---

## 5. Dependency Rules (DAG)

To prevent circular dependencies, dependencies must flow **downward only**:

```text
           [ apps/api ]       [ apps/worker ]
                │                    │
                └─────────┬──────────┘
                          ▼
┌───────────────────┬───────────────────┐
│   packages/wizard │ packages/insights │
└─────────┬─────────┴─────────┬─────────┘
          │                   │
          ▼                   │
  [ packages/engine ] ────────┘
          │
          ▼
   [ packages/core ]   (Base - Zero local dependencies)
```

---

## 6. Implementation Blueprint for Coding Agent

### Step 1: Root Workspace Initialization
Root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "packages/*",
    "apps/*",
]
```

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
    "metis-engine",
    "typer>=0.9.0",
    "rich>=13.0.0",
]

[project.scripts]
metis-wizard = "metis.wizard.cli:app"

[tool.uv.sources]
metis-core = { workspace = true }
metis-engine = { workspace = true }

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
Developers and automated CI scripts can invoke each component's CLI directly using `uv run`:

```bash
# Run interactive wizard setup
uv run metis-wizard init

# Run evaluation directly on a trace log file
uv run metis-engine run --trace-file ./tests/fixtures/langfuse_trace.json

# View aggregated terminal insights report
uv run metis-insights report --results-file ./results.json
```

---

## 8. Next Steps for Coding Agent

1. Execute the initial workspace bootstrap shell command from Section 7.
2. Populate `pyproject.toml` files for all sub-packages using the Hatchling configuration blueprints in Section 6.
3. Wire package CLI entry points (`[project.scripts]`) using Typer in `src/metis/*/cli.py`.
4. Implement `metis.core` Pydantic models (`Trace`, `Span`, `Score`, `AssertionResult`) and interfaces.
5. Build `metis.engine` Langfuse trace parser and basic CLI evaluation execution logic (`uv run metis-engine`).
6. Run `uv sync` and verify imports work cleanly via `from metis.core import Trace`.
