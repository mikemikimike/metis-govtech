# Contributing to METIS

Thank you for contributing to METIS. This guide covers expectations and best practices for the monorepo — whether you're on the core team or contributing externally.

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

### Branching

All package work goes on a **release branch** named `<package>/v<semver>` (e.g., `engine/v0.2.0`). See [Versioning & Release](#versioning--release) below for the full flow.

For cross-cutting changes that don't belong to a single package (CI, root docs, contributing guide), use a short-lived descriptively-named branch (e.g., `update-ci-config`).

### Versioning & Release

Each package is versioned independently via a static `version` field in its `pyproject.toml`. Releases follow this flow:

1. **Create a release branch** named `<package>/<target-version>` off `main` (e.g., `engine/v0.2.0`). The version is decided upfront and the branch accumulates all commits destined for that release.
2. **Develop on the release branch** — add features, fixes, and tests scoped to this release. Intermediate commits follow normal commit message conventions.
3. **Merge to `main` when ready** — use a merge commit (not squash) to preserve the branch history.
4. **Tag the merge commit on `main`** with `<package-name>/v<semver>` (e.g., `metis-engine/v0.2.0`). Always tag the merge commit itself, not the last commit on the feature branch.

Key rules:
- The tag MUST live on `main` — never on a feature/release branch.
- One tag per package per release.
- Bump the `version` field in the package's `pyproject.toml` as part of the release branch work (not at merge time).
- Always use **annotated tags** (`git tag -a`), never lightweight tags. Annotated tags record the tagger, date, and message — lightweight tags are just pointers with no metadata.

### Tag Messages

Write a short summary line, optionally followed by a blank line and bullet points for detail:

```bash
git tag -a "metis-engine/v0.2.0" -m "Migrate orca-agentic-evals v0.2.0 into metis-engine

- Simulation harness (Playwright + LLM user agent)
- YAML experiment validation with JSON schema versioning
- Namespace rewrite: orca_agentic_evals → metis.engine"
```

Guidelines:
- First line: imperative mood, summarizes the release (≤72 chars).
- Body (optional): key additions, migrations, or breaking changes as bullet points.
- Write for someone scanning `git tag -n` output — be informative, not verbose.

For single-commit fixes that don't warrant a release branch, commit directly to a short-lived branch, merge, and tag as usual.

### Release Notes

Each package maintains a `CHANGELOG.md` at `packages/<name>/CHANGELOG.md`. Write entries as you develop on the release branch — not retroactively at merge time.

Format follows [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

## [0.2.0] — 2026-07-30

### Added
- Langfuse trace ingester for production observability

### Changed
- Score aggregation now handles missing span timestamps gracefully

### Fixed
- Crash when trace file contains empty spans

## [0.1.0] — 2026-06-15

Initial release.
```

Guidelines:
- Write for **consumers** of the package — focus on user-facing impact, not implementation details.
- Use the categories: Added, Changed, Deprecated, Removed, Fixed, Security.
- Each bullet should be a single sentence explaining what changed and why it matters.
- Include the release date (ISO 8601) when the version is merged and tagged.
- An `## [Unreleased]` section at the top is acceptable during development but must be replaced with the version number before merging.

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
- Tests covering the change
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

## Getting Help

- Architecture questions → [docs/architecture.md](docs/architecture.md)
- Build system → `make help`
- CLI usage → `metis --help`

If something in this guide is unclear or outdated, open an issue or fix it directly — contributions to docs are contributions too.
