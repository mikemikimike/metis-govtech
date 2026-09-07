# Migration Guide

This guide lists the changes a consumer must make to cross each **major** version
boundary. Each entry is a concrete old → new instruction. For the full record of
what changed and why, see the per-package changelogs (currently accumulated in
[`CHANGELOG.next.md`](CHANGELOG.next.md) during the v1 pre-release).

## How this guide is organized

Breaking changes only happen at **major** version bumps ([SemVer](https://semver.org/)),
so this guide has **one section per major boundary** — never a section per version pair:

- **Within a major line there is nothing to migrate.** `v1.0 → v1.4` is additive
  and fixes only, by contract. Just bump the version.
- **Multi-major jumps compose.** To go from v1 to v3, follow the `v1 → v2` section,
  then the `v2 → v3` section, in order. There is no dedicated "v1 → v3" section.
- **Each graduation appends one new section** (newest on top) and leaves older
  sections frozen as history.

So for `N` majors there are at most `N − 1` sections, not a permutation table.
(METIS packages version independently after v1.0, so a later section may cover a
single package's major bump rather than a coordinated one.)

This document is a **running file**: v1 breaking changes are recorded here as they
land on `next` (see [CONTRIBUTING.md](CONTRIBUTING.md)), and it ships with — and
survives past — the coordinated v1.0 release.

## Migrating to v1.0 (from v0.x)

### metis-wizard

#### `runs` renamed to `trials`

The execution-count concept is now called **trials** everywhere, to match the
evaluation glossary. The arithmetic is unchanged; only the names change.

**Python API**

- `ProductProfile.run_count()` → `ProductProfile.trial_count()`
- module `metis.wizard.application.runs` → `metis.wizard.application.trials`
- `format_runs()` → `format_trials()`

**Session files**

- The scenario card field `runs` is now `trials`.
- `SESSION_FORMAT_VERSION` advances from `5` to `6`. Session files at an older
  format version are refused with a clear message rather than auto-migrated —
  regenerate them with `metis wizard init`.

The compiled `experiment.yaml` is unchanged.

#### Profile models standardised on one shape

Every profile entity (task, behaviour, criterion, persona, scenario) now exposes
the same `name` + `description` pair through a shared `ProfileNode` base, and the
behaviour tick and the product summary are renamed for clarity.

**Python API**

- `Behaviour.statement` → `Behaviour.description`
- `Behaviour.priority` → `Behaviour.measured` (still a `bool` — the tick)
- `Product.summary` → `Product.description`
- `ProductProfile.ticked()` → `ProductProfile.measured_behaviours()`
- A criterion's `description` is now a structured `CriterionDescription`
  (`given` / `when` / `then`) instead of a flat string. Use
  `str(criterion.description)` for the old flat "Given …, when …, then …." text.

**Session files**

- Per-node authorship and generated-id history move off the profile onto the
  session (`SessionState.user_typed`, `SessionState.issued_ids`); profile nodes
  no longer carry authorship.
- `SESSION_FORMAT_VERSION` advances from `6` to `7`. Session files at an older
  format version are refused with a clear message rather than auto-migrated —
  regenerate them with `metis wizard init`.

The compiled `experiment.yaml` is unchanged.

### metis-core

_No breaking changes in v1.0._

### metis-library

_No breaking changes in v1.0._

### metis-engine

_No breaking changes in v1.0._

### metis-api

_No breaking changes in v1.0._
