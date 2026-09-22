# METIS Product Suite — Architecture Specification

## Table of Contents

- [1. Purpose & Scope](#1-purpose--scope)
- [2. Notation](#2-notation)
- [3. Technology Constraints](#3-technology-constraints)
- [4. Workspace Structure](#4-workspace-structure)
- [5. Component Specification](#5-component-specification)
- [6. Dependency Invariants](#6-dependency-invariants)
- [7. Testing Contract](#7-testing-contract)
- [8. Build Interface Contract](#8-build-interface-contract)
- [9. Versioning](#9-versioning)
- [10. CLI Interface](#10-cli-interface)

---

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
│   ├── library/
│   │   └── src/metis/library/
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
│   └── testbed/
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
| **Import Path** | `from metis.core import ...` |
| **Purpose** | Domain schemas, abstract interfaces, registry, and shared infrastructure. Zero external runtime dependencies beyond Pydantic v2. |

MUST NOT depend on any other workspace member.

---

### 5.2. `metis-library`

| | |
|---|---|
| **Import Path** | `from metis.library import ...` |
| **Purpose** | Shared catalog of metrics, skills, and reusable components consumed by both the execution path (engine) and the configuration path (wizard). The wizard references items by FQN; the engine resolves and executes them. Lightweight layer so consumers can enumerate catalog items without pulling in engine's heavier dependencies. |

MUST depend only on `metis-core`. MAY depend on evaluation framework libraries (DeepEval) required by the shared metric catalog.

---

### 5.3. `metis-engine`

| | |
|---|---|
| **Import Path** | `from metis.engine import ...` |
| **Purpose** | Evaluation runtime — ingests traces, executes metrics, produces evaluation reports. |

MUST depend on `metis-core` and `metis-library`. MAY depend on HTTP, math, parsing, browser automation, and LLM client libraries. MUST be usable both as a library import and as a standalone CLI.

---

### 5.4. `metis-wizard`

| | |
|---|---|
| **Import Path** | `from metis.wizard import ...` |
| **Purpose** | Interactive configuration generator for creating evaluation suites and guardrails. |

MUST depend on `metis-core` and `metis-library`. MUST NOT depend on `metis-engine`.

The wizard exposes a stateless Interview lifecycle interface (`handle_interview`,
`compile_profile`, `derive_stage`) and holds no server state: the Interview state is client-held and
travels whole on each operation. The wizard MUST NOT own an HTTP server or a frontend; a web client
reaches the Interview through `apps/api`. The CLI adapter drives the same lifecycle interface.

---

### 5.5. `metis-insights`

| | |
|---|---|
| **Import Path** | `from metis.insights import ...` |
| **Purpose** | Analytics computation and reporting engine for evaluation outputs. |

MUST depend on `metis-core`. MUST NOT depend on `metis-engine` or `metis-library`.

---

### 5.6. `metis-testbed`

| | |
|---|---|
| **Import Path** | `from metis.testbed import ...` |
| **Purpose** | Evaluator calibration and sandbox environment for running agents against controlled scenarios. |

MUST depend on `metis-core` and `metis-engine`.

---

### 5.8. `apps/api`

| | |
|---|---|
| **Import Path** | `from metis.api import ...` |
| **Purpose** | A thin, stateless HTTP door exposing METIS capabilities as a REST service. |

MAY depend on all `packages/*` members. For the wizard it depends on the `metis.wizard` public
Interview interface only (`apps/api -> metis.wizard`): the router calls `handle_interview`,
`compile_profile`, and the in-memory specification packager and maps typed results onto HTTP
responses. No stage, Profile, prompt, matching, fixture validation, or compilation rule lives in
the API. The package route accepts a Profile JSON part and request-scoped fixture bytes and returns
one `experiment.zip`; it retains no uploaded files.

**Client-held state boundary.** The service holds only immutable settings and model clients for the
process lifetime. It holds no Interview state: start creates state, turn carries the complete state
and one typed response, and end carries the complete state for best-effort completion. The next state
goes back whole in the response, so any instance serves any operation and no Interview file is
written. Web clients drive the wizard through these HTTP lifecycle routes; they MUST NOT embed the
wizard.

---

### 5.9. `apps/web`

| | |
|---|---|
| **Purpose** | Web frontend providing a graphical interface for METIS capabilities. |

MUST communicate exclusively with `apps/api` via REST. MUST NOT import or depend on any Python package directly.
The browser owns the local Interview record, fixture Blobs, and display transcript in IndexedDB. It
sends only the client-held `InterviewState` and typed responses to lifecycle routes; fixture bytes
are sent only for a request-scoped package operation. It MUST NOT depend on server Interview
resources, wizard static assets, or an embedded wizard runtime.

It MUST offer two authoring paths: the guided Interview, and a manual form for a user who already
knows the scorers to run. The manual form MUST stay flat: it MUST NOT surface Task, Behaviour, or
Criterion. It MUST build a valid `ProductProfile` in the browser and submit it to the existing
package route, and it MUST NOT add a route or create an Interview record. Server-side validation in
`metis-wizard` stays authoritative for both paths.

In this first version the manual form collects only what an engine run absolutely needs. The engine
runs from `experiment.yaml`; the fuller `ProductProfile` is consumed only at report generation, which
reads `inputs/profile.yaml`. The synthesized Profile is therefore minimal by design.

The normal local run uses two processes: `PORT=8001 uv run metis-api` and
`npm --prefix apps/web run dev`.
The Vite proxy uses `METIS_API_ORIGIN`, defaulting to `http://127.0.0.1:8001`.

---

## 6. Dependency Invariants

Dependencies MUST flow downward only. The following DAG is normative:

```text
[ apps/web ] ──HTTP──▶ [ apps/api ] ───────────────────────┐
                            │                               │
                            ▼                               ▼
                       [ packages/engine ] ◄── [ apps/testbed ]   [ packages/wizard ]
                            │         │                               │
                            │         ▼                               │
                            │   [ packages/insights ]                 │
                            │                                         │
                            ▼                                         ▼
                     [ packages/library ] ◄───────────────────────────┘
                            │
                            ▼
                     [ packages/core ]   (Base — zero local dependencies)
```

> `apps/web` has no compile-time dependency on any Python package. Its only runtime dependency is the HTTP API surface exposed by `apps/api`.

**Invariant Rules:**

1. `metis-core` MUST NOT depend on any other workspace member.
2. `metis-library` MUST depend only on `metis-core`.
3. `metis-wizard` MUST NOT depend on `metis-engine` or `metis-insights`.
4. `metis-insights` MUST NOT depend on `metis-engine`, `metis-library`, or `metis-wizard`.
5. `metis-engine` MUST NOT depend on `metis-wizard` or `metis-insights`.
6. No circular dependencies SHALL exist between any workspace members.
7. Upward dependencies (child depending on parent in the DAG) MUST NOT be introduced.
8. `apps/web` MUST NOT import or depend on any Python workspace member at compile time.

---

## 7. Testing Contract

### Directory Layout

```text
tests/
├── unit/                       # Per-package isolation tests
│   ├── core/
│   ├── library/
│   ├── engine/
│   ├── wizard/
│   └── insights/
├── integration/                # Cross-package flow tests
└── fixtures/                   # Shared test data
    ├── langfuse_trace.json
    └── experiment.yaml
```

The web client workflow and its deferred features are documented in
[`docs/guide/web.md`](guide/web.md).

### Rules

- Unit tests (`tests/unit/<package>/`) MUST test a single package in isolation. External dependencies SHOULD be mocked.
- Integration tests (`tests/integration/`) MUST verify cross-package flows.
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
| `web-check` | Run non-mutating `apps/web` formatter, type checker, tests, and API drift checks. |
| `web-build` | Run the production `apps/web` build. This target writes the normal Vite output. |
| `ci` | Composition: `check` + `web-check` + `web-build` + `test`. MUST mirror what CI pipelines execute. |
| `clean` | Remove all generated/cached files across the monorepo. |

**Rules:**

- All targets MUST operate from the workspace root.
- The `ci` target MUST be the single command that reproduces a CI pipeline run locally.
- `check` and `web-check` MUST be non-mutating (read-only verification).

---

## 9. Versioning

The workspace uses **independent semantic versioning** — each package maintains its own version, and releases are tracked with scoped git tags.

### 9.1. Design Rationale

Independent versioning is chosen over a unified "METIS version" for the following reasons:

- Each package is owned by a separate engineer. Per-package versions serve as a coordination and project management signal per team.
- Lightweight consumers can pin and track just the packages they depend on.

**Tradeoffs:**

- There is no single unified "METIS version" — the product identity is a tuple of package versions.
- Git tags form a flat interleaved stream across packages.
- A **compatibility manifest** (`COMPATIBILITY.md` at the workspace root) SHOULD be maintained to record which package versions have been validated together as a working set.

### 9.2. Mechanism

Each package declares a static `version` field in its `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]

[project]
name = "metis-engine"
version = "0.2.0"
```

The `pyproject.toml` is the single source of truth for each package's version.

### 9.3. Rules

- All packages MUST declare a static `version` field in `pyproject.toml`. No package MAY use dynamic version derivation.
- All versions MUST be SemVer-compliant (`MAJOR.MINOR.PATCH`).

### 9.4. Git Tag Convention

Released versions are marked with scoped annotated git tags:

- **Format:** `<package-name>/v<semver>` (e.g., `metis-engine/v0.2.0`, `metis-core/v0.1.0`)
- **Creation:** `git tag -a metis-engine/v0.2.0 -m "metis-engine v0.2.0"`
- **Per-package listing:** `git tag -l "metis-engine/*"`

Tags are markers, not sources of truth. The `version` field in `pyproject.toml` is authoritative.

### 9.5. Tag-on-Merge Rule

Every merge to `main` that modifies source code under `packages/` or `apps/` MUST be tagged with a scoped version bump for the affected package(s).

- Multi-package PRs MUST receive one tag per affected package.
- **Exemption:** Merges that only touch root-level files (docs, CI config, `Makefile`, `.github/`, `infra/`) do NOT require a tag.

### 9.6. Release Workflow

1. Bump `version` in the affected package's `pyproject.toml`.
2. Commit the version bump as part of the PR (or as the merge commit).
3. Tag the merge commit: `git tag -a <package-name>/v<version> -m "<package-name> v<version>"`.
4. Push with `--tags`.

### 9.7. Commit Message Convention

All commits on `main` MUST be prefixed with the affected scope:

```text
engine: fix trace parsing for nested spans
core: add Span.duration computed field
wizard: update prompt templates for v2 schema
docs: update architecture spec versioning section
ci: add tag enforcement check
infra: update Docker base image
```

Package scopes (`core`, `library`, `engine`, `wizard`, `insights`, `api`, `web`) correspond to versioned artifacts and require a tag. Cross-cutting scopes (`docs`, `ci`, `infra`) do not.

### 9.8. CLI Version Reporting

The unified `metis --version` SHOULD print a breakdown of all installed component versions:

```text
metis 0.1.0
  core    0.1.0
  library 0.1.0
  engine  0.2.0
  wizard  0.1.0
```

### 9.9. Schema Versioning

Schema versions (for data formats like `experiment.yaml` and `session-record.json`) are independent integers maintained in source code constants, not tied to package versions.

---

## 10. CLI Interface

The primary user-facing CLI is the unified `metis` command, which composes sub-package CLIs under `metis <package> <subcommand>`.

Per-package standalone commands (e.g., `metis-engine`, `metis-wizard`) MUST also be available for CI or isolated installs.
