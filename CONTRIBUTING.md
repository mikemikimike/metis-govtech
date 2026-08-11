# Contributing to METIS

Thank you for contributing to METIS. This guide covers expectations and best practices for the monorepo — whether you're on the core team or contributing externally.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Monorepo Orientation](#monorepo-orientation)
- [Development Workflow](#development-workflow)
- [Code Standards](#code-standards)
- [Testing](#testing)
- [Adding New Packages or Extensions](#adding-new-packages-or-extensions)
- [Pull Requests](#pull-requests)
- [Dependency Rules](#dependency-rules)
- [Versioning & Release](#versioning--release)
- [Getting Help](#getting-help)

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (workspace and package manager)
- [direnv](https://direnv.net/) (optional — auto-activates the virtualenv)

## Getting Started

```bash
git clone <repo-url>
cd metis
make install    # installs all workspace packages + dev tools
make check      # verify everything passes (lint + format + typecheck)
```

If you use direnv, the `.envrc` will activate the virtualenv automatically. Otherwise, prefix commands with `uv run` or activate `.venv` manually.

## Monorepo Orientation

```
metis/
├── packages/           # Reusable library packages
│   ├── core/           # Domain schemas, interfaces, registry
│   ├── library/        # Shared catalog (metrics, skills, etc.)
│   ├── engine/         # Evaluation runtime + trace ingesters
│   └── wizard/         # Interactive config generator
├── apps/               # Deployable services (Stage 3+)
├── docs/               # Architecture spec, design docs
├── metis_cli.py        # Unified CLI entry point
└── pyproject.toml      # Workspace root
```

Dependencies flow **downward only**:

```
engine ──► library ──► core
wizard ──► library ──► core
insights ───────────────► core
```

For the full specification (component contracts, dependency invariants, versioning), see [docs/architecture.md](docs/architecture.md).

## Development Workflow

For the step-by-step GitHub collaboration playbook (branching, PRs, reviews, merging), see [docs/github-workflow.md](docs/github-workflow.md).

### Branching

Branch off `main` with a descriptive prefix:

| Prefix | Use |
|--------|-----|
| `feat/` | New functionality |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code restructuring (no behavior change) |
| `test/` | Adding or improving tests |

Example: `feat/langfuse-ingester`, `fix/score-validation`

### Running Checks

```bash
make check          # lint + format-check + typecheck (non-mutating)
make fix            # auto-fix lint + format
make ci             # full CI suite (check + test)
```

Run `make check` before pushing. CI will reject PRs that fail.

### Commit Messages

Use concise, imperative-mood messages that explain **why**, not just what:

```
add Langfuse trace ingester for production observability
fix score aggregation when spans have missing timestamps
```

Avoid generic messages like "fix bug" or "update code".

## Code Standards

| Concern | Tool | Notes |
|---------|------|-------|
| Linting | Ruff | All rules enforced in `pyproject.toml` |
| Formatting | Ruff | Single style, no debate |
| Type checking | Pyright | Strict mode; all public APIs must be typed |
| Data models | Pydantic v2 | All shared domain objects |
| CLIs | Typer + Rich | Sub-app composition pattern |

### Conventions

- **Namespace imports:** `from metis.core import ...`, `from metis.engine import ...`
- **Static version fields:** Each package declares `version = "X.Y.Z"` in its `pyproject.toml` (no dynamic derivation)
- **Package source layout:** `packages/<name>/src/metis/<name>/`

## Testing

```bash
make ci                 # run everything
uv run pytest           # full suite
uv run pytest tests/unit/core/   # single package
```

### Where Tests Go

| Type | Location | Scope |
|------|----------|-------|
| Unit | `tests/unit/<package>/` | Single package in isolation |
| Integration | `tests/integration/` | Cross-package flows |
| Fixtures | `tests/fixtures/` | Shared sample data (traces, configs) |

### Guidelines

- Unit tests should mock external dependencies, not sibling packages.
- Use shared fixtures from `tests/fixtures/` — don't inline large test data.
- New functionality should include tests. Bug fixes should include a regression test.

## Adding New Packages or Extensions

METIS is designed for extensibility at two main points:

- **Custom metrics** — implement `BaseMetric` from `metis.core` and register via `MetricRegistry`
- **Custom trace ingesters** — implement `BaseTraceIngester` and register via the `metis.trace_ingesters` entry point group

For details on contracts and constraints, see the [Architecture Specification](docs/architecture.md).

When adding a new workspace package:

1. Create the directory under `packages/<name>/src/metis/<name>/`
2. Add a `pyproject.toml` following the existing pattern (hatchling with static `version`)
3. Respect the dependency DAG — no upward or circular dependencies
4. Register it in the root `pyproject.toml` workspace members

## Pull Requests

### Before Opening

- [ ] `make check` passes locally
- [ ] New code has tests
- [ ] No unrelated changes bundled in

### What Reviewers Look For

- Adherence to the dependency DAG (no upward imports)
- Type annotations on public APIs
- Focused scope — one concern per PR

### Merging

PRs require at least one approval. CI must pass. Squash-merge is preferred for single-concern branches; merge commits are acceptable for larger feature branches with meaningful intermediate commits.

## Dependency Rules

These invariants are **non-negotiable** — CI will enforce them:

1. `metis-core` has zero workspace dependencies
2. `metis-library` depends only on `metis-core`
3. `metis-engine` and `metis-wizard` depend on `core` + `library` but NOT on each other
4. `metis-insights` depends only on `metis-core`
5. No circular dependencies, ever

When in doubt, check the DAG in [docs/architecture.md](docs/architecture.md).

## Versioning & Release

Each package is versioned independently via a static `version` field in its `pyproject.toml`. For the step-by-step release procedure, see [docs/github-workflow.md](docs/github-workflow.md#completing-a-release).

The naming conventions are:
- **Branch:** `release/<package-name>/v<semver>` (e.g., `release/metis-engine/v0.2.0`)
- **Tag:** `<package-name>/v<semver>` (e.g., `metis-engine/v0.2.0`)
- **Issue title:** `<package-name>/v<semver>`

The `release/` prefix on branches prevents ambiguity with identically-named tags.

Key rules:
- The tag MUST live on `main` — never on a feature/release branch.
- One tag per package per release.
- Bump the `version` field in the package's `pyproject.toml` as part of the release branch work (not at merge time).
- Always use **annotated tags** (`git tag -a`), never lightweight tags. Annotated tags record the tagger, date, and message — lightweight tags are just pointers with no metadata.

### Release Make Targets

The following targets automate release setup:

```bash
make release-init   PKG=engine VER=0.2.1   # Create branch (release/metis-engine/v0.2.1) + tracking issue
make release-branch PKG=engine VER=0.2.1   # Create branch only
make release-issue  APP=api    VER=1.0.0   # Create issue only
```

Use `PKG=<name>` for workspace packages (`packages/`) or `APP=<name>` for apps (`apps/`).

Platform detection is automatic (GitHub/GitLab via remote URL). Override with `PLATFORM=github|gitlab` for self-hosted instances. If no CLI is available, the formatted issue is printed to stdout for manual pasting.

> **GitLab users:** Symlink `docs/templates/release-issue.md` to `.gitlab/issue_templates/release-issue.md` for UI integration.

> **First-time setup:** Create the required labels on your repo before first use:
> ```bash
> # GitHub
> gh label create release --description "Release tracking" --color 0E8A16
> gh label create package --description "Workspace package" --color BFD4F2
> gh label create app --description "Deployable app" --color D4C5F9
> gh label create metis-core --description "" --color C5DEF5
> gh label create metis-library --description "" --color C5DEF5
> gh label create metis-engine --description "" --color C5DEF5
> gh label create metis-wizard --description "" --color C5DEF5
> gh label create metis-insights --description "" --color C5DEF5
> gh label create metis-api --description "" --color C5DEF5
>
> # GitLab
> glab label create release --description "Release tracking" --color 0E8A16
> glab label create package --color BFD4F2
> glab label create app --color D4C5F9
> glab label create metis-core --color C5DEF5
> glab label create metis-library --color C5DEF5
> glab label create metis-engine --color C5DEF5
> glab label create metis-wizard --color C5DEF5
> glab label create metis-insights --color C5DEF5
> glab label create metis-api --color C5DEF5
> ```

## Getting Help

- Architecture questions → [docs/architecture.md](docs/architecture.md)
- Build system → `make help`
- CLI usage → `metis --help`

If something in this guide is unclear or outdated, open an issue or fix it directly — contributions to docs are contributions too.
