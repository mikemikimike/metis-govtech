# METIS Product Suite — Architecture Specification

## 1. Purpose & Scope

METIS (Measurement and Evaluation of Trustworthy Intelligent Systems) is an extensible agentic evaluation suite designed for whole-of-government adoption. It enables agency teams to build fast while ensuring AI safety, alignment, and operational reliability by default.

This document is the normative architectural specification for the METIS suite. It defines system boundaries, component contracts, dependency invariants, and the build interface. All implementation artifacts (code, configuration, CI pipelines) MUST conform to this specification.

---

## 2. Notation

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 3. Technology Constraints

| Concern | Requirement |
|---------|-------------|
| Workspace & Package Management | MUST use `uv` workspaces with a single root lockfile (`uv.lock`). |
| Data Modeling & Validation | MUST use Pydantic v2 for all shared domain objects. |
| Namespace Packaging | MUST use Hatchling with PEP 420 native namespace packages. |
| CLI Framework | MUST use Typer + Rich for all CLI surfaces. |
| Database / ORM (Web Backend) | TBD. Under consideration: PostgreSQL + SQLAlchemy v2 (async) + Alembic. *(Stage 4)* |
| Task Queue (Async Processing) | TBD. Under consideration: Celery or ARQ backed by Redis. *(Stage 4)* |
| API Framework | TBD. Under consideration: FastAPI. *(Stage 4)* |
| Python Version | MUST target Python ≥ 3.11. |

---

## 4. Workspace Structure

The workspace is a Python monorepo. Directory names on disk are kept short (`packages/core`); code within each package uses the nested namespace layout (`src/metis/core`). All packages share a unified `metis` Python namespace.

```text
metis/
├── pyproject.toml              # Workspace root definition
├── metis_cli.py                # Unified CLI entry point (composes sub-package CLIs)
├── uv.lock                     # Single lockfile for the entire workspace
│
├── packages/                   # Reusable library packages
│   ├── core/
│   │   └── src/metis/core/
│   ├── metrics/
│   │   └── src/metis/metrics/
│   ├── engine/
│   │   └── src/metis/engine/
│   ├── wizard/
│   │   └── src/metis/wizard/
│   └── insights/
│       └── src/metis/insights/
│
├── apps/                       # Deployable application services
│   ├── api/
│   │   └── src/metis/api/
│   └── worker/
│       └── src/metis/worker/
│
└── infra/                      # Docker Compose, Kubernetes, deployment assets
```

**Rules:**

- Each package MUST contain a `pyproject.toml` at its root and source code under `src/metis/<pkg>/`.
- The root project MUST explicitly list all workspace members as dependencies so that `uv sync` installs them into the virtualenv.
- There MUST be exactly one lockfile (`uv.lock`) at the workspace root.

---

## 5. Component Specification

### 5.1. `metis-core`

| | |
|---|---|
| **Import Path** | `from metis.core import Trace, Score, BaseMetric, MetricRegistry, ExperimentConfig` |
| **CLI Command** | None |
| **Purpose** | Single source of truth for domain objects, contracts, and shared infrastructure. |

**Constraints:**

- MUST have zero external runtime dependencies beyond Pydantic v2 and the Python standard library.
- MUST NOT depend on any other workspace member.

**Public Contract:**

- Schema definitions: `Trace`, `Span`, `Step`, `ToolCall`, `Score`, `AssertionResult`, `EvaluationReport`.
- Configuration schema: `ExperimentConfig`, `MetricConfig`, `DataSourceConfig`.
- Enums: `EvaluationCategory`, `StepType`, `Status`, `SeverityLevel`.
- Abstract base interfaces: `BaseMetric`, `BaseTraceIngester`, `BaseEvaluator`.
- Registry: `MetricRegistry` — central lookup for metric implementations by name.
- Plugin discovery: `discover_ingesters()` / `ingest_trace()` — loads `BaseTraceIngester` implementations via the `metis.trace_ingesters` entry point group.
- Exceptions: `TraceParsingError`, `MetricExecutionError`, `InvalidConfigError`.

---

### 5.2. `metis-metrics`

| | |
|---|---|
| **Import Path** | `from metis.metrics import DEFAULT_REGISTRY, TrajectoryCompleteness` |
| **CLI Command** | None |
| **Purpose** | Built-in library of default metric implementations. |

**Rationale for Separation:**

`metis-metrics` exists as a standalone package rather than being bundled into `metis-engine` so that lightweight consumers (e.g., `metis-wizard`, custom metric authors, CI lint jobs) can enumerate and inspect available metrics without pulling in the engine's heavier runtime dependencies (`httpx`, `numpy`, trace ingestion machinery). Bundling metrics into engine would force every downstream consumer to inherit engine's full dependency tree — a classic transitive dependency problem that defeats the purpose of a modular workspace.

**Constraints:**

- MUST depend only on `metis-core`.
- MUST NOT introduce external runtime dependencies beyond those inherited from `metis-core`.

**Public Contract:**

- `DEFAULT_REGISTRY`: a pre-populated `MetricRegistry` containing all built-in metrics.
- Built-in metric implementations (e.g., `TrajectoryCompleteness`, `ToolCallAccuracy`, guardrail pass-rate).
- Metric authoring utilities (decorators, base helpers) for teams writing custom metrics.

---

### 5.3. `metis-engine`

| | |
|---|---|
| **Import Path** | `from metis.engine import Evaluator` |
| **CLI Command** | `metis-engine` |
| **Purpose** | Standalone execution engine for running evaluations against traces. |

**Constraints:**

- MUST depend on `metis-core` and `metis-metrics`.
- MAY depend on lightweight HTTP, math, and parsing libraries (e.g., `httpx`, `numpy`).
- MUST be usable both as a library import and as a standalone CLI.

**Public Contract:**

- Ships built-in trace ingesters (Langfuse, OpenTelemetry) registered via `[project.entry-points."metis.trace_ingesters"]`.
- CLI: `metis-engine run --trace-file <path>`.
- Loads metrics from the registry and executes them against normalized traces.

**Extension Point — Custom Trace Ingesters:**

Third-party packages MAY provide additional trace ingesters by implementing `BaseTraceIngester` from core and registering via the `metis.trace_ingesters` entry point group.

---

### 5.4. `metis-wizard`

| | |
|---|---|
| **Import Path** | `from metis.wizard import ConfigGenerator` |
| **CLI Command** | `metis-wizard` |
| **Purpose** | Interactive configuration generator for creating evaluation suites and guardrails. |

**Constraints:**

- MUST depend on `metis-core` and `metis-metrics`.
- MUST NOT depend on `metis-engine`.

**Public Contract:**

- Interactive CLI terminal UI for generating valid suite configuration YAML files.
- CLI: `metis-wizard init`.
- Template generation for custom metric authors.

---

### 5.5. `metis-insights`

| | |
|---|---|
| **Import Path** | `from metis.insights import AnalyticsEngine` |
| **CLI Command** | `metis-insights` |
| **Purpose** | Analytics computation and reporting engine for evaluation outputs. |

**Constraints:**

- MUST depend on `metis-core`.
- MUST NOT depend on `metis-engine` or `metis-metrics`.
- MAY depend on data analysis libraries (e.g., `pandas`).

**Public Contract:**

- Consumes `EvaluationReport` (from `metis.core`).
- Terminal-based analytics rendering (ASCII tables, pass/fail summaries).
- CLI: `metis-insights report --results-file <path>`.
- Programmatic reporting calculations for the API backend.

---

### 5.6. `metis-testbed` *(Deferred — Stage 4)*

| | |
|---|---|
| **Import Path** | `from metis.testbed import Sandbox` |
| **CLI Command** | TBD |
| **Purpose** | Evaluator calibration and sandbox environment for running agents against controlled scenarios. |

**Constraints:**

- MUST depend on `metis-core` and `metis-engine`.

**Public Contract:**

- Controlled execution environments for agent calibration.
- Scenario definitions for known-good/known-bad agent trajectories.
- Calibration utilities for tuning metric thresholds.

> Deferred to Stage 4. The MVP evaluates pre-recorded traces; live sandbox execution comes later.

---

### 5.7. `apps/api` *(Deferred — Stage 3)*

| | |
|---|---|
| **Purpose** | Web backend exposing METIS capabilities as a service. |

**Constraints:**

- MUST expose REST endpoints for configuration, trace submission, and fetching insights reports.
- MAY depend on all `packages/*` members.

> Deferred to Stage 3. The MVP is CLI-first.

---

### 5.8. `apps/worker` *(Deferred — Stage 5)*

| | |
|---|---|
| **Purpose** | Asynchronous job processor for long-running evaluation workloads. |

**Rationale:**

Trace evaluation can be computationally expensive — parsing large traces, executing many metrics, calling out to LLM-as-judge endpoints. Running these inline within an API request would block the HTTP thread, degrade latency, and risk timeouts. The worker decouples submission from execution: the API enqueues an evaluation request, and the worker picks it up and runs `metis.engine` in the background. This separation allows independent scaling of API throughput and evaluation compute.

**Constraints:**

- MUST import and execute evaluations via `metis.engine`.
- MUST consume jobs from a task queue.
- MAY depend on all `packages/*` members.

> Deferred to Stage 5. Only needed once evaluation workloads outgrow synchronous API handling.

---

## 6. Dependency Invariants

Dependencies MUST flow downward only. The following DAG is normative:

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
            [ packages/core ]   (Base — zero local dependencies)
```

**Invariant Rules:**

1. `metis-core` MUST NOT depend on any other workspace member.
2. `metis-metrics` MUST depend only on `metis-core`.
3. `metis-wizard` MUST NOT depend on `metis-engine` or `metis-insights`.
4. `metis-insights` MUST NOT depend on `metis-engine`, `metis-metrics`, or `metis-wizard`.
5. `metis-engine` MUST NOT depend on `metis-wizard` or `metis-insights`.
6. No circular dependencies SHALL exist between any workspace members.
7. Upward dependencies (child depending on parent in the DAG) MUST NOT be introduced.

---

## 7. Testing Contract

### Directory Layout

```text
tests/
├── unit/                       # Per-package isolation tests
│   ├── core/
│   ├── metrics/
│   ├── engine/
│   ├── wizard/
│   └── insights/
├── integration/                # Cross-package flow tests
└── fixtures/                   # Shared test data
    ├── langfuse_trace.json
    └── experiment.yaml
```

### Rules

- Unit tests (`tests/unit/<package>/`) MUST test a single package in isolation. External dependencies SHOULD be mocked.
- Integration tests (`tests/integration/`) MUST verify cross-package flows (e.g., ingesting a trace through the engine and producing a report).
- Test fixtures (`tests/fixtures/`) MUST hold shared sample data. Tests MUST NOT embed fixture data inline when a shared fixture exists.
- The full test suite MUST be runnable via `uv run pytest` from the workspace root.
- Per-package test runs MUST be supported: `uv run pytest tests/unit/<package>/`.

---

## 8. Build Interface Contract

A root `Makefile` MUST provide the following targets as the public development and CI interface:

| Target | Behavior |
|--------|----------|
| `install` | Install all workspace dependencies (including dev group). |
| `lint` | Run Ruff lint checks. MUST fail on violations. |
| `lint-fix` | Apply Ruff lint autofixes. |
| `format` | Format all Python files with Ruff. |
| `format-check` | Check formatting without modifying files. MUST fail on violations. |
| `fix` | Apply lint autofixes and format (convenience composition). |
| `typecheck` | Run Pyright type checking. MUST fail on errors. |
| `test` | Run the full test suite via pytest. |
| `test-unit` | Run unit tests only. |
| `test-integration` | Run integration tests only. |
| `check` | Composition: `lint` + `format-check` + `typecheck`. |
| `ci` | Composition: `check` + `test`. MUST mirror what CI pipelines execute. |
| `clean` | Remove all generated/cached files across the monorepo. |

**Rules:**

- All targets MUST operate from the workspace root. No per-package `cd` is required.
- The `ci` target MUST be the single command that reproduces a CI pipeline run locally.
- `check` MUST be non-mutating (read-only verification).
- Additional targets MAY be added, but the above set is REQUIRED.

---

## 9. CLI Interface

The primary user-facing CLI is the unified `metis` command, which composes sub-package CLIs:

```text
metis wizard init
metis engine run --trace-file <path>
metis insights report --results-file <path>
metis engine -V
```

Per-package standalone commands (`metis-engine`, `metis-wizard`, `metis-insights`) MUST also be available for CI or isolated installs.

---

## 10. Stages

| Stage | Scope | Status |
|-------|-------|--------|
| **Stage 1 — MVP** | `core`, `metrics`, `engine` (CLI evaluation of pre-recorded traces) | Active |
| **Stage 2 — Developer Experience** | `wizard`, `insights` (configuration generation, reporting) | Planned |
| **Stage 3 — Web Platform** | `apps/api` (REST service exposing METIS capabilities) | Deferred |
| **Stage 4 — Generalized METIS** | `testbed` (live sandbox, agent calibration) | Deferred |
| **Stage 5 — Scale** | `apps/worker` (async job processing for heavy evaluation workloads) | Deferred |
