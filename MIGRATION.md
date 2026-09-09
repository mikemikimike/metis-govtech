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

The compiled `experiment.yaml` is unchanged.

#### The interview is now stateless and file-free

The Interview no longer holds server-side state or writes a file. A caller runs one
lifecycle operation at a time and holds the returned state itself. This replaces the old
server-owned session file and its `SESSION_FORMAT_VERSION` / `INTERVIEW_FORMAT_VERSION`
machinery, which are gone.

**Python API**

- Call `handle_interview(request, interviewer=..., matcher=...)` with an
  `InterviewStartRequest`, `InterviewTurnRequest`, or `InterviewEndRequest`. It returns the next
  `InterviewState` with a derived stage, or a typed
  failure with a stable error code and the caller's state unchanged.
- Call `compile_profile(profile)` to get the `profile.yaml` and `experiment.yaml`
  strings in memory.
- Read progress with `derive_stage(state)`; there is no stored stage.

**What to change:** hold the `InterviewState` the last operation returned and send it back
on the next operation. Do not look for a session id or a saved file. Old server-owned
`session.json` / `interview_state.json` files are not read or migrated — start a new
interview.

#### `InterviewStep.PRIORITISE` removed

The separate prioritisation step is gone. Behaviour review and measurement selection
are now one step: every wizard-created Behaviour starts selected for measurement, and
the user clears the ones they do not want. The interview now shows five steps.

**What to change:** nothing in a caller; the step is internal. Any code or fixture
that named `PRIORITISE` must drop it.

#### The wizard no longer serves HTTP

`metis-wizard` no longer serves its own HTTP door or frontend. These are removed:

- the stateful web server and its per-interview store;
- the `/api/interviews` and `/api/interviews/{interview_id}` routes;
- the server-owned interview state files;
- the committed React frontend bundle served by the wizard;
- the `metis-wizard serve` command;
- the wizard FastAPI, Uvicorn, and multipart dependencies.

**Where it went:** the new [`metis-api`](#metis-api) service is the HTTP door.

**What to change:** point web clients at `metis-api`. Run it with the `metis-api`
executable, or the `apps/api/Dockerfile` built from the repository root.

### metis-core

_No breaking changes in v1.0._

### metis-library

_No breaking changes in v1.0._

### metis-engine

_No breaking changes in v1.0._

### metis-api

New package in v1.0 — the stateless HTTP door over the wizard. It replaces the
wizard-owned web server (see [The wizard no longer serves HTTP](#the-wizard-no-longer-serves-http)).
It is stateless — each turn or end request carries the whole client-held state — and exposes
`POST /api/v1/wizard/interview/start`, `POST /api/v1/wizard/interview/turn`,
`POST /api/v1/wizard/interview/end`, `POST /api/v1/wizard/compile`, and `/health`. There is no
prior version to migrate from; point web clients here.

### metis-web

The wizard web client now lives in `apps/web` and is a separate Node project. Replace commands that
previously targeted the retired web project with `npm --prefix apps/web run dev`,
`npm --prefix apps/web run build`, and `npm --prefix apps/web run check:api`. Start `metis-api` on
port 8001 (or set `METIS_API_ORIGIN` for another origin). Interview lists, state, and the display
transcript are browser-local; there is no server Interview list to migrate and no cross-device state.
Use `make web-check` for non-mutating web checks and `make web-build` for the production bundle.
The web gets optional metric details from `GET /api/v1/metrics` after a Profile contains a
Criterion. Direct authoring, fixture persistence, ZIP packaging, source analysis, hosted state,
authentication, and evaluation execution remain deferred.
