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

### Target branch: `next` vs. `v0.x`

METIS is preparing a coordinated v0 → v1.0 major bump across all packages. That work lives on a
long-lived **`next`** integration branch, tracked by the [v1.0 development plan](https://github.com/govtech-responsibleai/metis/issues/221).
Pick your target branch by the kind of change:

| Change | Branch off | PR into |
|--------|-----------|---------|
| v1 feature or breaking change | `next` | `next` |
| v0 bugfix / patch | `v0.x` | `v0.x` |

**`next` is an exception zone.** For the whole v1 pre-release phase the release ceremony is
suspended so engineers can move fast:

- **No release branches, tracking issues, or tags on `next`.** The `release/<pkg>/v<semver>`
  workflow and `make release-*` targets below apply to released lines (`v0.x`), not `next`.
- **Every package version is frozen at `1.0.0a1`.** Do not bump or tag it per change — it flips to
  `1.0.0` once, at graduation. It is an honest "unstable v1 pre-release" marker, not a progress counter.
- **Breaking changes are cheap** — no deprecation dance. Record each one in `MIGRATION.md`.
- **Changelog entries go in one combined file.** Add v1 entries to the temporary
  [`CHANGELOG.next.md`](CHANGELOG.next.md) at the repo root (grouped by package), **not** to the
  per-package `CHANGELOG.md` files. Those keep their v0.x history untouched on `next`. At graduation the
  combined file is split back into each package's `CHANGELOG.md` under a `## [1.0.0]` heading and deleted.
- **Code review and `make ci` still apply.** Only the release ceremony is dropped.
- **Pull relevant v0 fixes into `next` by cherry-picking** the fix commit from `v0.x` — never
  full-merge (that drags in v0 version commits and conflicts on every package's `version` line).

**`v0.x` keeps the normal release workflow** — `release/<pkg>/v0.x.y` branches and `<pkg>/v0.x.y`
tags, critical/security fixes only. On `v0.x`, write CHANGELOG entries per package during development,
as normal; on `next`, use the combined `CHANGELOG.next.md` (see above), which is split back into the
per-package files at graduation. When `next` stabilizes it merges to `main` in a single
coordinated bump, and the normal release workflow resumes on `main`. See
[docs/version-maintenance.md](docs/version-maintenance.md) for the graduation and v0.x maintenance procedure.

> **⚠️ Remove at graduation.** This whole "Target branch" section, the root `CHANGELOG.next.md`, and
> every other `next` / `1.0.0a1` mention across the repo are temporary pre-release scaffolding. When
> `next` merges to `main`, strip them per the
> [graduation cleanup checklist](docs/version-maintenance.md#graduating-next-to-main).

### Running Checks

```bash
make check          # lint + format-check + typecheck (non-mutating)
make fix            # auto-fix lint + format
make ci             # full CI suite (check + test)
```

Run `make check` before pushing. CI will reject PRs that fail.

When you change a wizard HTTP request or response, update the Pydantic contract in
`packages/wizard` first. Then regenerate the committed web types with
`npm --prefix apps/web run generate:api` and run `npm --prefix apps/web run check:api`. Do not edit
`apps/web/src/generated/api.ts` by hand.

### Commit Messages

We follow a convention for commit messages [borrowed from Deis/CoreOS/AngularJS](https://github.com/deis/deis/blob/master/CONTRIBUTING.md#commit-style-guideline). The format is:

```
{type}({scope}): {subject}

{body}

{footer}
```

**Rules:**

- `{type}` is one of: `feat`, `fix`, `docs`, `style`, `ref`, `test`, `chore`
- `{scope}` is the affected package or app name (e.g., `core`, `engine`, `wizard`, `api`)
- `{subject}` uses imperative present tense ("change", not "changed"), no capital first letter, no trailing dot
- Subject line limited to **50 characters**; body lines limited to **72 characters**
- `{body}` explains the motivation and contrasts with previous behavior
- `{footer}` mentions any breaking changes with migration notes

**Examples:**

```
feat(engine): add Langfuse trace ingester for production observability

fix(core): handle missing timestamps in score aggregation

chore(wizard): initialize release v0.4.0
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

Each package is versioned independently via a static `version` field in its `pyproject.toml`. For the step-by-step release procedure, see [docs/github-workflow.md](docs/github-workflow.md#completing-a-release). For coordinated major version bumps and maintenance branches, see [docs/version-maintenance.md](docs/version-maintenance.md).

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
> gh label create metis-core --description "" --color C5DEF5
> gh label create metis-library --description "" --color C5DEF5
> gh label create metis-engine --description "" --color C5DEF5
> gh label create metis-wizard --description "" --color C5DEF5
> gh label create metis-insights --description "" --color C5DEF5
> gh label create metis-api --description "" --color C5DEF5
>
> # GitLab
> glab label create release --description "Release tracking" --color 0E8A16
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
