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
│   ├── web/                    # TypeScript/React frontend (separate toolchain)
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   └── testbed/                # Live sandbox — Stage 4
│       └── src/metis/testbed/
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
| **Purpose** | Shared metric catalog consumed by both the execution path (`metis-engine`) and the configuration path (`metis-wizard`). |

**Architectural Role:**

`metis-metrics` is the convergence point between two otherwise independent subsystems: `metis-engine` (which executes metrics against traces) and `metis-wizard` (which presents metrics to users during configuration). Both need to enumerate, inspect, and reference the same set of metrics — but neither should depend on the other. `metis-metrics` provides that shared catalog as a lightweight, dependency-free layer that both can import independently.

**Rationale for Separation:**

This package exists as a standalone layer rather than being bundled into `metis-engine` so that lightweight consumers (e.g., `metis-wizard`, custom metric authors, CI lint jobs) can enumerate and inspect available metrics without pulling in the engine's heavier runtime dependencies (`httpx`, `numpy`, trace ingestion machinery). Bundling metrics into engine would force every downstream consumer to inherit engine's full dependency tree — a classic transitive dependency problem that defeats the purpose of a modular workspace.

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

### 5.8. `apps/web` *(Deferred — Stage 3)*

| | |
|---|---|
| **Purpose** | Web frontend providing a graphical interface for METIS capabilities. |

**Technology Stack:**

| Concern | Requirement |
|---------|-------------|
| Language | TypeScript (strict mode) |
| UI Framework | React 18+ |
| Build Tooling | Vite |
| Component Library | TBD. Under consideration: Radix UI + Tailwind CSS. |
| State Management | TBD. Under consideration: TanStack Query for server state, Zustand for client state. |
| Routing | TBD. Under consideration: TanStack Router or React Router. |

**Constraints:**

- MUST communicate exclusively with `apps/api` via its REST endpoints. MUST NOT import or depend on any Python package directly.
- MUST be a standalone single-page application (SPA) deployable independently of the API backend.
- MUST support configuration of API base URL via environment variable (e.g., `VITE_API_BASE_URL`).
- SHOULD provide feature parity with CLI workflows for non-developer users (trace submission, report viewing, suite configuration).

**Public Contract:**

- Dashboard: overview of evaluation runs, pass/fail trends, metric distributions.
- Trace submission: upload trace files or connect to trace sources for evaluation.
- Report viewer: interactive exploration of `EvaluationReport` data (drill-down by metric, trace, step).
- Suite configuration: visual editor for experiment YAML (wrapping wizard capabilities).

> Deferred to Stage 3 alongside `apps/api`. The frontend is a consumer of the API — it does not exist without a running backend.

---


## 6. Dependency Invariants

Dependencies MUST flow downward only. The following DAG is normative:

```text
[ apps/web ] ──HTTP──▶ [ apps/api ]
                            │
                            ▼
                       [ packages/engine ] ◄── [ apps/testbed ]
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

> `apps/web` has no compile-time dependency on any Python package. Its only runtime dependency is the HTTP API surface exposed by `apps/api`.

**Invariant Rules:**

1. `metis-core` MUST NOT depend on any other workspace member.
2. `metis-metrics` MUST depend only on `metis-core`.
3. `metis-wizard` MUST NOT depend on `metis-engine` or `metis-insights`.
4. `metis-insights` MUST NOT depend on `metis-engine`, `metis-metrics`, or `metis-wizard`.
5. `metis-engine` MUST NOT depend on `metis-wizard` or `metis-insights`.
6. `metis-testbed` MUST depend on `metis-core` and `metis-engine`. MUST NOT depend on `metis-wizard` or `metis-insights`.
7. No circular dependencies SHALL exist between any workspace members.
8. Upward dependencies (child depending on parent in the DAG) MUST NOT be introduced.
9. `apps/web` MUST NOT import or depend on any Python workspace member at compile time. Its sole integration point is the HTTP API exposed by `apps/api`.

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
│   ├── insights/
│   └── testbed/
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

## 9. Versioning

The workspace uses a **unified version** — all packages share a single version derived from git tags. Individual package versions are not maintained independently.

### 9.1. Mechanism

Version is derived at build time via `hatch-vcs`, which reads the most recent git tag matching `v*` (e.g., `v0.1.0`). Each package's `pyproject.toml` declares:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]

[project]
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"
raw-options.root = "../.."   # relative path to workspace root
```

The root `pyproject.toml` uses the same plugin without the `root` override:

```toml
[tool.hatch.version]
source = "vcs"
```

### 9.2. Rules

- All packages MUST use `hatch-vcs` as their version source. No package MAY declare a static `version` field.
- Released versions MUST correspond to an annotated git tag (`git tag -a v0.1.0`).
- Untagged builds produce a dev suffix (e.g., `0.1.0.dev3+gabcdef`), distinguishing development builds from releases automatically.
- The `metis -V` / `metis --version` CLI output MUST reflect the VCS-derived version.

### 9.3. Rationale

Independent per-package versioning adds coordination overhead (which packages to bump, compatibility matrices between workspace members) without benefit while:

- All packages are consumed together via the monorepo.
- No package is published to PyPI independently.
- The project is pre-1.0.

This decision SHOULD be revisited if individual packages are published to an external registry for third-party consumption.

### 9.4. Future: Independent Package Versioning

If the need arises to version packages independently (e.g., publishing `metis-core` to PyPI for third-party metric authors), the migration path is:

1. Replace `dynamic = ["version"]` + `hatch-vcs` with a static `version` field in the target package's `pyproject.toml`.
2. Add explicit compatible-release constraints for intra-workspace dependencies (e.g., `metis-core >= 1.2.0`).
3. Adopt a bump policy — either manual (developer bumps the version when the package's public contract changes) or automated via conventional-commit tooling (e.g., `python-semantic-release`, `commitizen`) that scopes commits to packages and computes SemVer bumps per package.
4. All versions MUST remain SemVer-compliant. A breaking change in a dependency (e.g., `metis-core` major bump) requires downstream packages to update their constraint and cut their own release.

**CLI Version Reporting:**

No code changes are required in the CLI layer when migrating to independent versions. Each package already resolves its own version via `importlib.metadata.version("<package-name>")`, and per-package CLIs (e.g., `metis engine -V`) already report their specific version. Once independent versions are active, `metis --version` SHOULD print a breakdown of all installed component versions:

```text
metis 2.0.0
  core    1.3.0
  metrics 1.1.0
  engine  2.0.0
  wizard  1.2.0
```

---

## 10. CLI Interface

The primary user-facing CLI is the unified `metis` command, which composes sub-package CLIs:

```text
metis wizard init
metis engine run --trace-file <path>
metis insights report --results-file <path>
metis testbed run --scenario <name>   # Stage 4 — TBD
metis engine -V
```

Per-package standalone commands (`metis-engine`, `metis-wizard`, `metis-insights`, `metis-testbed`) MUST also be available for CI or isolated installs.

---

## 11. Stages

| Stage | Scope | Status |
|-------|-------|--------|
| **Stage 1 — MVP** | `core`, `metrics`, `engine` (CLI evaluation of pre-recorded traces) | Active |
| **Stage 2 — Developer Experience** | `wizard`, `insights` (configuration generation, reporting) | Planned |
| **Stage 3 — Web Platform** | `apps/api` (REST service exposing METIS capabilities) | Deferred |
| **Stage 4 — Generalized METIS** | `testbed` (live sandbox, agent calibration) | Deferred |
