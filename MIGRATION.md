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

### Execution folders

Engine creates `experiments/execute/<id>-YYYYMMDD-HHMMSS/`. Trial records and artifacts
live under `outputs/trials/`. Engine results and Insights reports share `outputs/reports/`.
Inputs and logs remain at the execution root. Keep `--input-dir` for new executions
and `--experiment-dir` for evaluation and resume. Pass the full
`outputs/reports/results.json` path to Insights.

Create new executions from the original input folder when possible. To retain an
existing execution, move its trial and report folders under `outputs/`. Update each
`Artifact.path` in trial records from `trials/...` to `outputs/trials/...`, including
artifacts embedded in conversation turns. Keep `inputs/...` paths unchanged. Update
artifact manifest paths and trial log links to their new locations. Move the whole
execution under `experiments/execute/` if desired. These changes are not automatic.
The CLI rejects the earlier root-level trial and report layout.

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
- Put each Grader FQN and argument map on its Criterion as `grader_fqn` and
  `grader_args`. Use separate Criteria for different requirements or settings.
  Every Criterion needs a Grader, including dormant Criteria.
- Keep only ID, name, and description on each Scenario. Create a Task for each
  selected Scenario and Persona pair. Move fixtures and Trial counts to that Task.
  Select measured Behaviours with `behaviour_refs`. Give each Task a unique ID.
  Every selected Behaviour supplies all its Criteria and must have at least one.
- Derive coverage through Task → Behaviour. Every Scenario needs a
  Task, and every measured Behaviour needs coverage. Engine execution limits keep
  their defaults.
- Use `InterviewState.specification` for the complete document. For `/package`, send the
  full final Interview state in the `state` form field. For manual exports, send the
  user-authored Specification in the `specification` form field. Send exactly one source.
- Use `/compile` response keys `specification.yaml` and `specification`. Retain the returned
  Specification so later edits keep Task IDs. Exports put the YAML and `fixtures/` under
  `outputs/`. Pass that folder to Engine as `--input-dir`. Interview exports save the final
  state as `inputs/interview_state.json`; manual exports include an empty `inputs/` folder.
- The default CLI design root is `experiments/design/YYYYMMDD-HHMMSS-interview/`.
  Explicit `--out-dir` paths remain exact. Resume now requires `--out-dir <design-root>`.
  Downloads use timestamped `interview` or `manual` ZIP names and contain one matching root
  folder. Extract them into `experiments/design/`.
- For an interrupted CLI Interview saved with the earlier layout, move `interview_state.json`
  into `inputs/` before calling `resume`. Move existing fixture files into `outputs/fixtures/`.
  Keep Task fixture references relative to that folder. Completed CLI exports retain the state;
  `outputs/specification.yaml` marks completion.
- Recreate old browser drafts with the current format. Old drafts with `state.profile` or without Tasks are
  not valid current Interview state. There is no automatic conversion.
- Start a new run after conversion. Old run records have no Task/Criterion identity
  and cannot supply the current result attribution. Resume uses the frozen new
  specification. Report plans now contain `tasks`; scores and evidence retain
  Task, Trial, Criterion, Grader FQN, and Grader arguments.

The domain `Task` below was previously used for a product function. That older
concept is now `Feature`. The current Task is an explicit Test Case.

#### Update pre-release Task references

Replace each `tasks[].criterion_refs` list with `tasks[].behaviour_refs`.
Find the parent Behaviour for each selected Criterion. Keep each Behaviour ID once.
Review the result because a selected Behaviour runs all its Criteria.
Keep `schema_version: 2` and start a new run with the converted document.
Recreate saved Interviews whose Tasks use Criterion references. The browser keeps
these records in storage and shows that they cannot be read. It does not convert
pending controls or delete fixture data.

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
| `scenarios[].metric_refs` | One Criterion for each Grader, with `grader_fqn` and `grader_args`. Tasks select their parent Behaviours with `tasks[].behaviour_refs`. |
| `scenarios[].max_turns`, `timeout_minutes`, `response_wait_ms`, `max_run_retries` | Move each value to the same field on every Task for that Scenario. |
| Profile `scenarios[].behaviour_refs` | Move to `tasks[].behaviour_refs` on each Task for that Scenario. |

Check these points when you convert a file:

- **Trial count default.** The old Scenario default for `num_trials` was `1`. The
  Task default is `3`. If an old Scenario did not set `num_trials`, set
  `num_trials: 1` on its Tasks to keep the same number of Trials.
- **Execution limits.** Tasks accept optional `max_turns`, `timeout_minutes`,
  `response_wait_ms`, and `max_run_retries`. Their defaults are `20`, `15`,
  `300000`, and the runner's retry default. Set `max_run_retries: 0` to disable
  run retries. Move explicit Scenario values to each corresponding Task.
  A Grader argument such as `TurnBudgetGrader` `max_turns` sets the passing
  budget only. The Task's `max_turns` controls execution.
- **Grader formats.** The old `metric_refs` item had three formats. Each becomes
  one Criterion:

  | Old `metric_refs` item | Criterion fields |
  |---|---|
  | `metis.library.graders.X` | `grader_fqn: metis.library.graders.X`, `grader_args: {}` |
  | `metis.library.graders.X: {max_turns: 4}` | `grader_fqn: metis.library.graders.X`, `grader_args: {max_turns: 4}` |
  | `{class: metis.library.graders.X, args: {...}}` | `grader_fqn: metis.library.graders.X`, `grader_args: {...}` |

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
            grader_fqn: metis.library.graders.TurnBudgetGrader
            grader_args:
              max_turns: 4
  # AC-ORCA-2 already exists under Orchestration Behaviour EB-ORCA-2. It now has
  # grader_fqn: metis.library.graders.DirectHandleRecognitionGrader.

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
    behaviour_refs: [EB-ORCA-2, EB-EXEC-1]
  - id: TC-002
    scenario_ref: direct-question
    persona_ref: impatient-executive
    fixtures: []
    num_trials: 3
    behaviour_refs: [EB-ORCA-2, EB-EXEC-1]
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

#### `Criterion.metric_fqn`/`metric_args` renamed to `grader_fqn`/`grader_args`

**Python API**

- `Criterion.metric_fqn` → `Criterion.grader_fqn`
- `Criterion.metric_args` → `Criterion.grader_args`

**On disk**

- Every `specification.yaml`'s `metric_fqn:`/`metric_args:` Criterion keys are now
  `grader_fqn:`/`grader_args:`. Old files are not migrated — update them by hand or
  recompile.

### metis-library

#### `metrics` subpackage renamed to `graders`

"Metric" never appears in `GLOSSARY.md`; the glossary's term for a procedure that evaluates
a trial against a criterion is **Grader**.

**Python API**

- Import path `metis.library.metrics` → `metis.library.graders`
- Base classes `MetisTurnMetric`/`MetisSessionMetric` → `MetisTurnGrader`/`MetisSessionGrader`
- Every `*Metric`-suffixed class → its `*Grader` equivalent, e.g.
  `metis.library.metrics.TurnBudgetMetric` → `metis.library.graders.TurnBudgetGrader`. The
  fallback judge `metis.library.metrics.default.CriterionGEvalMetric` →
  `metis.library.graders.default.CriterionGEvalGrader`.

### metis-engine

#### Schema versions are now `2`

v1 marks its break from v0 with one schema version bump. `specification.yaml`, run records
(`record.json`), and the report schema (`Report v2`) now use version `2`. Set
`schema_version: 2` in each `specification.yaml`. The engine refuses run records from v0;
run the simulation again to create new records.

Report JSON now uses `features` at the root, in `resultTable`, and in trial outcome
items. Update report consumers and regenerate reports.

#### `Run*` renamed to `Trial*`

The individual-execution concept, previously misnamed `Run` throughout the engine, is
now `Trial` everywhere, matching the glossary ("Run" means a grouping of repeated
Trials of the same Test Case — not touched by this change; it stays conceptual, with
no stored object).

**Python API**

- `RunConfig` → `TrialConfig`, `RunOutcome` → `TrialOutcome`, `RunFailure` →
  `TrialFailure`, `RunRecord` → `TrialRecord`, `RunMeta` → `TrialMeta`
- `RunRecoverableError` → `TrialRecoverableError`
- `RunRetryConfig` → `TrialRetryConfig` (and the Playwright runner's own `RetryConfig`
  fields `run_max_retries`/`run_retry_delay_seconds` → `trial_max_retries`/
  `trial_retry_delay_seconds`)
- `RunPlanItem` → `TrialPlanItem`; `run_experiment()` → `execute_experiment()`;
  `expand_run_plan()` → `expand_trial_plan()`; `run_folder_name()` → `trial_folder_name()`
- `Orchestrator.run()` → `Orchestrator.execute()`
- `Scenario.max_run_retries` → `Scenario.max_trial_retries` (engine-internal only — the
  public `Task.max_run_retries` field in `specification.yaml` is unchanged)

**On disk**

- The experiment-output `runs/<scenario>-<persona>-<trial>/` directory is now
  `trials/<scenario>-<persona>-<trial>/`. Old `record.json` files under the old `runs/`
  directory are not migrated or read — run the simulation again to produce
  `trials/`-rooted output under the new field names.

**Report JSON**

- `PlanTask.sessionsPlanned` → `trialsPlanned`; `PlanTask.sessionsRun` → `trialsRun`.

#### `Metric*` renamed to `Grader*`

Every `Metric`-named symbol in the engine is now `Grader`, matching `metis-library`'s
rename and the glossary.

**Python API**

- `MetricRef` → `GraderRef`; `Scenario.metric_refs`/`TrialConfig.metric_refs` → `grader_refs`
- `MetricPassRate` → `GraderPassRate`; `UnmappedMetric` → `UnmappedGrader`
- `MetricResult` → `GraderResult`; `SessionMetricResult`/`TurnMetricResult` →
  `SessionGraderResult`/`TurnGraderResult`
- `EvalDurations.turn_metrics_seconds`/`session_metrics_seconds` →
  `turn_graders_seconds`/`session_graders_seconds`

**Report JSON**

- `Scores.metricPassRate` → `graderPassRate`; `PlanTask.metricsAsked`/`metricsScored` →
  `gradersAsked`/`gradersScored`
- `EvidenceItem.metric_fqn`/`metric_args` → `grader_fqn`/`grader_args`
- `AxisRow.metrics` → `graders`; `ResultTableColumn.metric` → `grader`
- `Timings.turn_metrics_seconds`/`session_metrics_seconds` →
  `turn_graders_seconds`/`session_graders_seconds`
- `unmapped[].metric` → `unmapped[].grader`

#### Report generation moved to `metis insights report`

`metis engine evaluate` and `run` no longer write `reports/report.json` or
`reports/report.html`. They write `reports/results.json` and print the command that
builds the report:

```bash
metis insights report --results-file experiments/<run>/reports/results.json
```

Scripts that read `report.json` after `evaluate` must run that command first.

**Python API**

- `metis.engine.generate_report` and `metis.engine.ReportResult` are removed. Evaluate,
  then call `metis.insights.save_report(results, experiment_dir)` with an
  `metis.core.reporting.EvaluationResults`, or run the CLI command above.
- `metis.engine.reporting` is removed. `Report`, `build_report`, and
  `load_report_sources` are now in `metis.insights`. `TurnReport`, `SessionReport`,
  `TurnGraderResult`, and `SessionGraderResult` are now in `metis.core.reporting`.
- `report.schema.json` moved from `packages/engine/schemas/` to
  `packages/insights/schemas/`. Its content and version (`Report v2`) are unchanged.

### metis-api

New package in v1.0 — the stateless HTTP door over the wizard. It replaces the
wizard-owned web server (see [The wizard no longer serves HTTP](#the-wizard-no-longer-serves-http)).
It is stateless — each turn or end request carries the whole client-held state — and exposes
`POST /api/v1/wizard/interview/start`, `POST /api/v1/wizard/interview/turn`,
`POST /api/v1/wizard/interview/end`, `POST /api/v1/wizard/compile`,
`POST /api/v1/wizard/package`, and `/health`. There is no prior version to migrate from; point web
clients here.

#### `GET /api/v1/metrics` renamed to `GET /api/v1/graders`

**What to change:** point clients at `/api/v1/graders`. The response shape is unchanged —
only the path and the `MetricSummary` → `GraderSummary` schema name change.

### metis-web

The wizard web client now lives in `apps/web` and is a separate Node project. Replace commands that
previously targeted the retired web project with `npm --prefix apps/web run dev`,
`npm --prefix apps/web run build`, and `npm --prefix apps/web run check:api`. Start `metis-api` on
port 8001 (or set `METIS_API_ORIGIN` for another origin). Interview lists, state, and the display
transcript and fixture Blobs are browser-local; there is no server Interview list to migrate and no
cross-device state. A completed Interview downloads one `specification.zip` containing
`specification.yaml` and its validated `fixtures/` files. The API retains no fixture bytes.
Use `make check-web` for non-mutating web checks and `make build-web` for the production bundle.

The grader catalogue route the web client calls is now `GET /api/v1/graders`
(`api.graders()` in `transport/api.ts`, was `api.metrics()`). `Criterion.grader_fqn`/
`grader_args` wire fields were `metric_fqn`/`metric_args`.
The web gets optional grader details from `GET /api/v1/graders` after a Specification contains a
Criterion. The manual form supports direct authoring. Source analysis, hosted state,
authentication, and evaluation execution remain deferred.


## Evaluation subject: Product → Target (#429)

- Import `Target` and `TargetProfile` from `metis.core.profile` in place of
  `Product` and `ProductProfile`. Use `Specification.target` and `profile.target`.
- Change the top-level `product` key to `target` in specification YAML, API JSON,
  and saved Interview state. Change patch and form paths from `product.*` to
  `target.*`. The missing-data code is now `target_incomplete`.
- Report JSON uses `target` for the report name and each conversation response.
  Target failures use `failureSource: "target"`. Regenerate reports from results
  after updating their saved `inputs/specification.yaml`.
- Browser storage upgrades saved Interviews automatically. It updates the
  specification key and form paths, and preserves user text and file bytes.
  Other clients must update their saved state before sending it to the API.

Specification schema version remains `2` under the `next` pre-release policy.
