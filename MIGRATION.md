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

### Shared specification (core, engine, wizard, API, and web)

Use `metis.core.profile.ProductProfile` for Product context, Features, Behaviours,
and Criteria. Use `metis.core.experiment.Experiment` for the execution plan.
`metis.core.specification.Specification` combines both.
The wizard persistence model is `metis.wizard.domain.specification.Specification`.

Merge the old `profile.yaml` and `experiment.yaml` into `specification.yaml`.
Keep `schema_version: 2` on `next`. Use the complete example in
`packages/engine/example-experiment/specification.yaml` as the reference.

- Keep `id` and `runner_factory_ref`. Use `product.description` for the description.
- Keep the Product → Feature → Behaviour → Criterion hierarchy and `measured` state.
- Put each Grader FQN and argument map on its Criterion as `metric_fqn` and
  `metric_args`. Use separate Criteria for different requirements or settings.
  Every Criterion needs a Grader, including dormant Criteria.
- Keep only ID, name, and description on each Scenario. Create a Task for each
  selected Scenario and Persona pair. Move fixtures and Trial counts to that Task.
  Select Criteria with `criterion_refs`. Give each Task a unique, ID.
- Derive coverage through Task → Criterion → Behaviour. Every Scenario needs a
  Task, and every measured Behaviour needs coverage. Engine execution limits keep
  their defaults.
- Use `InterviewState.specification` for the complete document and the
  `specification` form field for `/package`.
- Use `/compile` response keys `specification.yaml` and `specification`. Retain the returned
  Specification so later edits keep Task IDs. ZIP exports contain one YAML and `fixtures/`.
- Recreate old browser drafts with the current format. Old drafts with `state.profile` or without Tasks are
  not valid current Interview state. There is no automatic conversion.
- Start a new run after conversion. Old run records have no Task/Criterion identity
  and cannot supply the current result attribution. Resume uses the frozen new
  specification. Report plans now contain `tasks`; scores and evidence retain
  Task, Trial, Criterion, Grader FQN, and Grader arguments.

The domain `Task` below was previously used for a product function. That older
concept is now `Feature`. The current Task is an explicit Test Case.

#### From `experiment.yaml` to `specification.yaml`

Use this table to find where each `experiment.yaml` field goes. Profile fields
(`product`, `features`, and Criteria) move into the same file without change,
except for the Criterion Grader fields in the table.

| Old field | New field |
|---|---|
| `description` (top level) | `product.description` |
| `personas[].id`, `personas[].description` | Same fields. Add the new required `name`. |
| `scenarios[].id`, `scenarios[].description` | Same fields. Add the new required `name`. |
| `scenarios[].persona_refs` | One Task for each Persona, with `tasks[].scenario_ref` and `tasks[].persona_ref` |
| `scenarios[].fixtures` | `tasks[].fixtures` on each of those Tasks |
| `scenarios[].num_trials` | `tasks[].num_trials` on each of those Tasks |
| `scenarios[].metric_refs` | One Criterion for each Grader, with `metric_fqn` and `metric_args`. Tasks select Criteria with `tasks[].criterion_refs`. |
| `scenarios[].max_turns`, `timeout_minutes`, `response_wait_ms`, `max_run_retries` | Move each value to the same field on every Task for that Scenario. |
| Profile `scenarios[].behaviour_refs` | Removed. Coverage comes from Task → Criterion → Behaviour. |

Check these points when you convert a file:

- **Trial count default.** The old Scenario default for `num_trials` was `1`. The
  Task default is `3`. If an old Scenario did not set `num_trials`, set
  `num_trials: 1` on its Tasks to keep the same number of Trials.
- **Execution limits.** Tasks accept optional `max_turns`, `timeout_minutes`,
  `response_wait_ms`, and `max_run_retries`. Their defaults are `20`, `15`,
  `300000`, and the runner's retry default. Set `max_run_retries: 0` to disable
  run retries. Move explicit Scenario values to each corresponding Task.
  A Grader argument such as `TurnBudgetMetric` `max_turns` sets the passing
  budget only. The Task's `max_turns` controls execution.
- **Grader formats.** The old `metric_refs` item had three formats. Each becomes
  one Criterion:

  | Old `metric_refs` item | Criterion fields |
  |---|---|
  | `metis.library.metrics.X` | `metric_fqn: metis.library.metrics.X`, `metric_args: {}` |
  | `metis.library.metrics.X: {max_turns: 4}` | `metric_fqn: metis.library.metrics.X`, `metric_args: {max_turns: 4}` |
  | `{class: metis.library.metrics.X, args: {...}}` | `metric_fqn: metis.library.metrics.X`, `metric_args: {...}` |

- **Where a Criterion goes.** Put the Criterion under the Behaviour that it
  measures, and set `measured: true` on that Behaviour. If a Criterion with the
  same requirement and Grader settings exists, select it. Do not add a second one.
  If no Behaviour fits, add one. The example adds `F-EXEC` and `EB-EXEC-1` for
  Graders that had no Criterion.

The example below shows part of the Orca `direct-question` Scenario before and
after conversion. The old Scenario has three Personas and seven Graders. The
example shows two Personas and two Graders.

Before, in `experiment.yaml`:

```yaml
scenarios:
  - id: direct-question
    description: Ask Orca the difference between a bar chart and a histogram.
    num_trials: 3
    persona_refs: [cooperative-delegator, impatient-executive]
    metric_refs:
      - metis.library.metrics.DirectHandleRecognitionMetric
      - metis.library.metrics.TurnBudgetMetric:
          max_turns: 4
```

After, in `specification.yaml`:

```yaml
features:
  - id: F-EXEC
    name: Execution checks
    description: Checks that had no matching Criterion.
    behaviours:
      - id: EB-EXEC-1
        name: Execution checks
        description: Additional checks selected for the evaluation.
        measured: true
        criteria:
          - id: AC-EXEC-3
            name: Turn budget
            description:
              given: an evaluation interaction
              when: the interaction is evaluated
              then: the session completed within the allowed turn budget
            metric_fqn: metis.library.metrics.TurnBudgetMetric
            metric_args:
              max_turns: 4
  # AC-ORCA-2 already exists under its Orchestration Behaviour. It now has
  # metric_fqn: metis.library.metrics.DirectHandleRecognitionMetric.

scenarios:
  - id: direct-question
    name: Direct question
    description: Ask Orca the difference between a bar chart and a histogram.

tasks:
  - id: TC-001
    scenario_ref: direct-question
    persona_ref: cooperative-delegator
    fixtures: []
    num_trials: 3
    criterion_refs: [AC-ORCA-2, AC-EXEC-3]
  - id: TC-002
    scenario_ref: direct-question
    persona_ref: impatient-executive
    fixtures: []
    num_trials: 3
    criterion_refs: [AC-ORCA-2, AC-EXEC-3]
```

The full converted file is
`packages/engine/example-experiment/specification.yaml`.


### metis-wizard

#### `Task` renamed to `Feature`

The Profile groups product functions under `features`. Update Python imports from `Task`
to `Feature` and from `TaskDraft` to `FeatureDraft`. Use `profile.features`,
`profile.feature(id)`, and `profile.feature_of(behaviour_id)`.

For each saved `profile.yaml`, rename the top-level `tasks` key to `features` and set
`schema_version` to `2`. Existing IDs can stay unchanged. New feature IDs use `F-`.
Update patch paths from `tasks[...]` to `features[...]`.

Saved browser Interviews that use profile schema version 1 cannot resume. Start a new
Interview. Keep a backup of any saved state before conversion; its pending patches and
history can also contain paths with `tasks[...]`.

The wizard compiles `specification.yaml` with `schema_version: 2`. Reports change too; see
[Schema versions are now `2`](#schema-versions-are-now-2).

#### `runs` renamed to `trials`

The execution-count concept is now called **trials** everywhere, to match the
evaluation glossary. The arithmetic is unchanged; only the names change.

**Python API**

- `ProductProfile.run_count()` → `Specification.trial_count()`
- module `metis.wizard.application.runs` → `metis.wizard.application.trials`
- `format_runs()` → `format_trials()`

#### Profile models standardised on one shape

Every named specification entity (feature, behaviour, criterion, persona, scenario) now exposes
the same `name` + `description` pair through a shared `NamedNode` base, and the
behaviour tick and the product summary are renamed for clarity.

**Python API**

- `Behaviour.statement` → `Behaviour.description`
- `Behaviour.priority` → `Behaviour.measured` (still a `bool` — the tick)
- `Product.summary` → `Product.description`
- `ProductProfile.ticked()` → `ProductProfile.measured_behaviours()`
- A criterion's `description` is now a structured `CriterionDescription`
  (`given` / `when` / `then`) instead of a flat string. Use
  `str(criterion.description)` for the old flat "Given …, when …, then …." text.

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
- Call `compile_specification(specification)` to get the `specification.yaml` string and the Specification
  with assigned Task IDs in memory.
- Call `package_specification(specification, fixtures)` to get one in-memory `specification.zip` with the
  validated fixture bytes under `fixtures/`.
- `SpecificationFixture` now takes a `stream` binary file object instead of a `content` byte
  string. The packager consumes streams in bounded chunks; the caller owns and closes them.
- Read progress with `derive_stage(state)`; there is no stored stage.

The start request accepts an optional `perspective` value. If it is omitted, the Interview uses
the `end_user` default. To choose a point of view, send one of `end_user`, `engineer`, `compliance`,
or `security`.

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

#### Schema versions are now `2`

v1 marks its break from v0 with one schema version bump. `specification.yaml`, run records
(`record.json`), and the report schema (`Report v2`) now use version `2`. Set
`schema_version: 2` in each `specification.yaml`. The engine refuses run records from v0;
run the simulation again to create new records.

Report JSON now uses `features` at the root, in `resultTable`, and in trial outcome
items. Update report consumers and regenerate reports.

### metis-api

New package in v1.0 — the stateless HTTP door over the wizard. It replaces the
wizard-owned web server (see [The wizard no longer serves HTTP](#the-wizard-no-longer-serves-http)).
It is stateless — each turn or end request carries the whole client-held state — and exposes
`POST /api/v1/wizard/interview/start`, `POST /api/v1/wizard/interview/turn`,
`POST /api/v1/wizard/interview/end`, `POST /api/v1/wizard/compile`,
`POST /api/v1/wizard/package`, and `/health`. There is no prior version to migrate from; point web
clients here.

### metis-web

The wizard web client now lives in `apps/web` and is a separate Node project. Replace commands that
previously targeted the retired web project with `npm --prefix apps/web run dev`,
`npm --prefix apps/web run build`, and `npm --prefix apps/web run check:api`. Start `metis-api` on
port 8001 (or set `METIS_API_ORIGIN` for another origin). Interview lists, state, and the display
transcript and fixture Blobs are browser-local; there is no server Interview list to migrate and no
cross-device state. A completed Interview downloads one `specification.zip` containing
`specification.yaml` and its validated `fixtures/` files. The API retains no fixture bytes.
Use `make check-web` for non-mutating web checks and `make build-web` for the production bundle.
The web gets optional metric details from `GET /api/v1/metrics` after a Specification contains a
Criterion. The manual form supports direct authoring. Source analysis, hosted state,
authentication, and evaluation execution remain deferred.
