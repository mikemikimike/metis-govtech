# Changelog — v1.0 pre-release (`next`)

> **Temporary, `next`-only file.** For the whole v1 pre-release phase, all v1
> changelog entries live here in one place instead of in each package's
> `CHANGELOG.md`. This avoids churning five separate changelog files (and the
> merge conflicts that come with them) while the API is still unstable.
>
> **Do not add v1 entries to the per-package `CHANGELOG.md` files while on
> `next`.** Those files keep their v0.x history untouched. At graduation, the
> entries below are split out — each package's section is folded into its own
> `CHANGELOG.md` under a `## [1.0.0]` heading — and this file is deleted. See
> [docs/version-maintenance.md](docs/version-maintenance.md#graduating-next-to-main)
> and [CONTRIBUTING.md](CONTRIBUTING.md#target-branch-next-vs-v0x).
>
> v0.x bugfixes cherry-picked into `next` are already recorded in the
> per-package changelogs on `v0.x`; do not duplicate them here.

The format is based on [Keep a Changelog](https://keepachangelog.com/). All
packages sit at a static `1.0.0a1` for the entire pre-release phase (see
[issue #221](https://github.com/govtech-responsibleai/metis/issues/221)); the
single `[1.0.0a1] — Unreleased` heading below is not bumped per change.

## [1.0.0a1] — Unreleased

### Build

#### Changed

- **`make install` no longer installs Playwright unconditionally.** The flat
  `install-playwright` target is replaced by `install-extras-playwright`, which
  first syncs `--extra playwright` before running `playwright install`. Use
  `make install-extras-playwright` (or `make install-engine`) to install the
  browser binary; `make install-extras` runs all optional extras.
  `install-playwright` is also removed from `packages/engine/Makefile`.
  **Note:** #335 (via PR #343) made a parallel fix to `v0.x` using the same
  `install-extras` model. When `v0.x` was cherry-picked into `next` (#396),
  `next`'s Makefiles were kept unchanged: they already contained every target
  #343 adds, and #343's `--extra web` does not exist on `next`.

### Docs

#### Changed

- **Clarified `GLOSSARY.md`'s Session definition.** A session now explicitly
  corresponds to exactly one trial: the target agentic system's conversation
  for a trial produces the traces that make up its session. This resolves an
  apparent naming overlap between `target_session_id`, the Langfuse
  session-grouping key, and `MetisSessionMetric` — they are the same concept
  once the one-to-one relationship with trial is stated. No code changes.
  ([#409](https://github.com/govtech-responsibleai/metis/issues/409))

### metis-core

#### Added

- Shared ProductProfile, Experiment, and Specification models. The Profile holds product
  requirements. The Experiment holds Personas, Scenarios, Tasks, and execution settings.
  The Specification combines both in one document (#395).

- `metis.core.reporting`: the serializable grader-result types (`TurnReport`,
  `SessionReport`, `TurnGraderResult`, `SessionGraderResult`) and `EvaluationResults`,
  the version-guarded `reports/results.json` file that `metis-engine` writes and
  `metis-insights` reads (#417).

#### Breaking

- Tasks use `behaviour_refs` to select measured Behaviours. Execution requires each selected Behaviour to have Criteria and evaluates all of them. Criterion score identity stays unchanged (#413).

- Rename `Criterion.metric_fqn`/`metric_args` to `grader_fqn`/`grader_args`, matching
  `GLOSSARY.md`'s **Grader** term for the concept these fields reference (#415).

### metis-library

#### Breaking

- Rename the `metis.library.metrics` subpackage to `metis.library.graders`, its two base
  classes `MetisTurnMetric`/`MetisSessionMetric` to `MetisTurnGrader`/`MetisSessionGrader`,
  and every `*Metric`-suffixed grader class (77 total, including the fallback judge
  `CriterionGEvalMetric` → `CriterionGEvalGrader`) to its `*Grader` equivalent — e.g.
  `TurnBudgetMetric` → `TurnBudgetGrader`. "Metric" never appears in `GLOSSARY.md`; the
  glossary's term for this concept is **Grader** (#415).

### metis-engine

#### Changed

- Resolve each Task's selected Behaviours to all their Criterion Graders, with separate Criterion IDs and settings in execution and saved Trial records (#413).

- Run, resume, evaluate, and report from `specification.yaml`. Execute explicit Tasks,
  preserve Criterion Grader arguments, and retain Task/Trial/Criterion identity in scores.
  Tasks carry optional turn, timeout, response wait, and run retry settings into execution.
  Include the full example experiment and a simple Orca API example with one Task
  and one Trial (#395).

- Rename report Task groups to Features, including report JSON fields and report labels (#392).

- Report generation now reads named Behaviours, measured state, and structured Criteria from
  the Specification in `specification.yaml`.

#### Breaking

- Set `schema_version` to `2` for `specification.yaml`, run records, and the report schema. v1 bumps
  each schema once to mark the break from v0, and later `next` changes keep version `2` (#392).

- Rename every `Run`-as-individual-execution symbol in `packages/engine/` to `Trial`
  (`RunConfig` → `TrialConfig`, `RunRecord` → `TrialRecord`, `RunOutcome` →
  `TrialOutcome`, `RunFailure` → `TrialFailure`, `RunMeta` → `TrialMeta`,
  `RunRecoverableError` → `TrialRecoverableError`, `RunRetryConfig` →
  `TrialRetryConfig`, and matching renames across the orchestrator, TUI state,
  structured logging, CLI resume classification, and report `trialsPlanned`/
  `trialsRun` fields), freeing "Run" for its glossary meaning — a grouping of
  repeated Trials of the same Test Case, conceptual only, no new class. Also
  renames `run_experiment()` to `execute_experiment()` and `Orchestrator.run()`
  to `Orchestrator.execute()` to avoid a noun/verb collision with the renamed
  `Run` concept. The on-disk `runs/<folder>/` experiment-output directory is
  now `trials/<folder>/` (#200).

- Rename every `Metric`-named symbol in `packages/engine/` to `Grader`
  (`MetricRef` → `GraderRef`, `MetricPassRate` → `GraderPassRate`, `UnmappedMetric` →
  `UnmappedGrader`, `MetricResult` → `GraderResult`, `SessionMetricResult`/`TurnMetricResult`
  → `SessionGraderResult`/`TurnGraderResult`, and matching renames across the orchestrator,
  CLI evaluation loop, and reporting pipeline), including report JSON fields
  `metricPassRate`/`metricsAsked`/`metricsScored` → `graderPassRate`/`gradersAsked`/
  `gradersScored`, `Scenario.metric_refs`/`TrialConfig.metric_refs` → `grader_refs`, and
  `Timings.turn_metrics_seconds`/`session_metrics_seconds` →
  `turn_graders_seconds`/`session_graders_seconds` (these measure grading wall-clock time,
  not an unrelated observability signal — confirmed in scope by issue #415) (#415).

- `evaluate` and `run` write `reports/results.json` and print the
  `metis insights report --results-file <path>` command instead of building the report.
  They no longer print the pass/fail/skip table or write `report.json`/`report.html`.
  `generate_report`, `ReportResult`, and the `metis.engine.reporting` subpackage are
  removed, and `report.schema.json` moved to `metis-insights` (#417).

### metis-insights

#### Added

- New package. `metis insights report --results-file <path>` reads an evaluation's
  `results.json`, prints the pass/fail/skip summary, and writes `report.json` and
  `report.html` into the same experiment's `reports/` directory. It owns `Report` and
  `report.schema.json`, and `make ci` checks that schema (#417).

#### Changed

- Expand Task Behaviour selections for plan counts, Criterion score attribution, and missing-result explanations (#413).

### metis-wizard

#### Added

- **Opening documents.** Flat Interview start requests can carry files as `{name, text?}`. The
  wizard keeps the opening description and document context in client-held state, with supported
  TXT, Markdown, PDF text-layer, and DOCX extraction through its facade. Prompts receive readable
  text and identify unread files. New Scenario drafts can suggest any opening file by name, and the
  existing Scenario review confirms each assignment.

- **ARC capability evidence at Interview start.** The CLI and headless interface now use the
  12-capability catalogue in three ordered groups. Start requires `known_capability_ids` and
  `capability_confidence`, records them in required client-held Interview context, and uses the
  confidence to guide Clarify and Behaviours probing. Every model call receives a synthesized
  catalogue background; the values do not enter `Specification`.

- Interview opening now offers End user, Engineer, Compliance, and Security perspectives. The
  selected perspective travels in client-held Interview context and guides the language and depth
  of model responses, with specific guidance for Clarify and Behaviours. Labels and questions are
  package configuration. The web client asks for the perspective; the CLI always uses End user.

- **JSON schema for Specification drafts.** `packages/wizard/schemas/specification.schema.json` is generated
  from the `Specification` model and CI-guarded by `make check-schema`, giving schema-aware
  editors autocomplete and validation for hand-authored drafts. The Specification carries a
  `schema_version` field (defaulted to `2`; an unreadable version is refused, not misread).
- **A stateless Interview lifecycle interface.** `handle_interview` accepts a start, turn, or end
  request against client-held state and returns the next state with a derived stage, or a typed
  failure with a stable error code and the caller's state unchanged. `compile_specification` turns a
  finished Specification into the `specification.yaml` string in memory, and
  `package_specification` returns a complete in-memory `specification.zip` with validated fixture bytes
  read from bounded streams.
  `derive_stage` computes progress from the Specification and two confirmation flags, so no stage is stored.
  The Interview state travels whole in each request and is never written to a file.
- **Wizard interface guides.** The Wizard guide now has separate CLI, web, and API paths. The API
  guide explains requests and responses through a worked Interview, with document handling and
  error recovery references.
- **Standardized wizard specification nodes.** Features, behaviours, criteria, personas, and scenarios use
  explicit `name` and `description` fields; criteria use structured Given/When/Then clauses;
  behaviour selection is `measured`; and Product uses `description`.

#### Fixed

- **Required product details.** Before behaviour review, the Interview shows a form for any
  missing product name or description. The user can supply these details and continue when the
  model has not supplied them.

#### Changed

- Draft, edit, copy, and validate Task Behaviour selections in the Interview. Export Behaviour references in the shared Specification (#413).

- Wizard prompts now group Features by main product functions and Behaviours by distinct
  expectations for success. Slide creation and revision share one Feature. Explicit deliverable
  instructions and content accuracy have separate scopes, with individual acceptance checks
  and coverage-based counts.

- Export one `specification.yaml` with Task references and Criterion Grader settings.
  Preserve IDs through edits, assign new IDs to copies, and validate Task coverage before
  export. Remove the compiler dependency on the engine package (#395).

- Clarify now explores the product widely before it goes deep, with one instruction set instead of a
  product phase and a machinery phase.
- Prompts now wrap injected reference content — the primer, the ARC catalogue, the Specification, the
  transcript, the perspective, the capability evidence, and the user's message — in a named
  XML-style tag. The system prompt identifies tagged content as reference material, not instructions.

- **Renamed the wizard control model from Session to Interview.** The runtime object and its state
  carry the Interview name: `Interview`, `InterviewState`, and `InterviewStep`.
- **Behaviour review and measurement are now one stage.** Every wizard-created Behaviour starts
  selected for measurement. One screen shows each Behaviour with its measurement control, and the
  user clears any Behaviour they do not want to measure. Continue needs at least one measured
  Behaviour and writes Criteria for that final subset only.
- **Renamed the "run" count to "trial", to agree with the evaluation glossary.** The glossary
  calls one execution a **trial**. The wizard called the total execution count
  (`Σ scenarios of personas × trials`) a "run count". This was wrong. The count is now a trial
  count on every surface: the domain method `Specification.run_count()` is now `trial_count()`,
  the `application/runs.py` module is now `trials.py` (`format_runs` → `format_trials`), and all
  interview, review-document and hand-authoring copy states "trials". The arithmetic does not
  change.
  ([#254](https://github.com/govtech-responsibleai/metis/issues/254))
- **Moved the wizard tests into the root `tests/` tree.** Unit tests now live under
  `tests/unit/wizard/`, integration tests under `tests/integration/wizard/`, and shared fixtures
  under `tests/fixtures/wizard/`, matching the documented repository convention. Test behaviour is
  unchanged.

#### Removed

- **The wizard no longer serves its own HTTP door or frontend.** The stateful web server, the
  per-interview store, the `metis-wizard serve` command, the committed React bundle, and the wizard
  FastAPI, Uvicorn, and multipart dependencies are gone. A web client now talks to the new
  `metis-api` service over HTTP. The interview itself — models, driver, screens, compiler — does not
  change.
- **`InterviewStep.PRIORITISE` is removed**, with its screen, transitions, and status. The interview
  now shows five steps.

#### Breaking

- Rename the wizard `Task` and `TaskDraft` models to `Feature` and `FeatureDraft`. Specifications use
  `features`, patch paths use `features[...]`, and new feature IDs use `F-`. Specification schema
  version 2, prompts, API types, browser forms, and reports use the glossary term (#392).

- **Interview state is client-held and file-free.** The server-owned session file, its format
  version, and the `/api/interviews` routes are gone. A caller holds the returned state and sends it
  back on the next operation. `InterviewState` carries the Specification, Interview context, two
  confirmation flags, bounded clarification history, authorship data, and at most one pending
  request. Context includes the perspective, capability evidence, opening description, and
  documents. The resolved-request transcript, stored step, and file methods are removed. Old
  session files are not migrated — start a new interview.

- Rename every `Metric`-named symbol in `packages/wizard/` to `Grader`
  (`MetricSpec`/`MetricParam`/`MetricSummary` → `GraderSpec`/`GraderParam`/`GraderSummary` in
  `contracts/metric_spec.py`, renamed to `contracts/grader_spec.py`; `METRICS_PACKAGE` →
  `GRADERS_PACKAGE`; the facade function `metric_catalogue()` → `grader_catalogue()`; and
  matching renames across the matcher, driver, screens, and compiler), and the fallback judge
  FQN `metis.library.metrics.default.CriterionGEvalMetric` →
  `metis.library.graders.default.CriterionGEvalGrader` (#415).

### metis-api

#### Added

- **Request-scoped document extraction.** `POST /api/v1/wizard/documents/extract` returns text or a
  typed error in the existing failure envelope. It closes uploaded streams and keeps no files or
  Interview state. The wizard configuration route also exposes the document limits.

- **Capability-aware wizard configuration and start.** `/api/v1/wizard/config` serves the ordered
  ARC capability catalogue, and `/api/v1/wizard/interview/start` accepts the complete description,
  known capability ids, confidence, and other opening choices.

- **New package: a stateless HTTP door over the wizard.** `POST /api/v1/wizard/interview/start`
  creates state from the raw product description, `POST /api/v1/wizard/interview/turn` applies one
  typed response, and `POST /api/v1/wizard/interview/end` performs best-effort completion.
  `POST /api/v1/wizard/compile` compiles a Specification; `/health` reports liveness. The service holds
  no Interview state — each turn or end request carries the whole client-held state — so any instance
  can serve any operation. Typed wizard results map to 200, 400, 422, 503, and 500, all in one error
  shape. Runs as
  the `metis-api` executable and ships with a `Dockerfile` built from the repository root.
- **Grader catalogue route.** `GET /api/v1/graders` returns installed grader summaries through the
  public wizard facade without user state or filesystem writes.
- **Wizard client configuration route.** `GET /api/v1/wizard/config` returns the package-owned
  Interview busy message, so HTTP clients do not copy wizard presentation text.
- **Specification package route.** `POST /api/v1/wizard/package` accepts a Specification and request-scoped
  fixture files and returns one `specification.zip` containing `specification.yaml` and an explicit
  `fixtures/` directory. The API retains no uploaded bytes.
- **Shared model environment names.** The API reads `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
  `INTERVIEW_MODEL`, matching the wizard and engine provider configuration, and can load one root
  `.env` for local development.

#### Changed

- Return `specification.yaml` and the Specification with assigned Task IDs from compile.
  Package one specification and its fixtures (#395).

- The wizard configuration payload now includes the opening question and the four perspective
  definitions. The Interview start request accepts an optional perspective and records it in the
  returned client-held context.
- **Moved the API tests into the root `tests/` tree.** Door tests now live under `tests/unit/api/`
  and end-to-end tests under `tests/integration/api/`, sharing the wizard's offline fixtures from
  `tests/fixtures/wizard/` directly instead of through a `sys.path` insertion. Test behaviour is
  unchanged.

#### Breaking

- Rename `GET /api/v1/metrics` to `GET /api/v1/graders`, and its response model
  `MetricSummary` to `GraderSummary` (#415).

### metis-web

#### Added

- **Opening documents.** A plus button in the composer opens a compact document tray. Original files
  stay in local Interview storage, and only files assigned to Scenarios enter the package.

- **Grouped capability opening controls.** The opening screen now displays all 12 ARC capabilities,
  lets the user select known capabilities (including none), requires Low, Medium, or High selection
  completeness confidence, and sends the full start request in one operation.

- **Standalone browser client.** The wizard UI now lives in `apps/web`, uses generated OpenAPI
  types and the stateless `apps/api` lifecycle routes, and stores local Interviews, fixture Blobs,
  and their display transcript in IndexedDB. The old wizard-owned web project and Python static
  output are retired.
- **Grader details.** The Specification pane can request the optional grader catalogue once per page load
  through `GET /api/v1/graders`; the rest of the Interview remains usable when that route fails.
- **Manual experiment authoring.** The opening screen offers a stateless form for
  Experiment details, Personas, Scenarios, and Test Cases. Each Test Case selects one
  Persona and one Scenario, with its own Trials, scorers, and files. The form retains
  assigned Task IDs and stores scorer settings on Criteria. It builds `specification.zip`
  with `specification.yaml` and fixtures through the existing API, without an Interview
  record (#395). When a field is not complete, **Download specification** marks each
  field that needs a change, shows what to change, and moves the focus to the first one.

#### Changed

- Use Behaviour references in manual authoring and show Behaviour selections in the Specification pane. Preserve incompatible saved Interviews and show them as unreadable (#413).

- The Specification pane shows Test Cases, their Trial counts, and file choices (#395).

- Each browser tab keeps its own Interview selection, with refresh and Back/Forward support.
  New tabs and windows start a new evaluation. Switching Interviews preserves question drafts and
  form values while the page stays open. Submitted replies, files, errors, and manual retries stay
  with their sender, including when another Interview is open. Interrupted sends require a manual
  retry, and a failed local save can be retried without another model call while the page is open.

- The opening screen now reads its question and perspective choices from the API configuration,
  asks who the evaluation is for with hover help, and sends the selected perspective on start.
- **Clear completion and output actions.** The conversation composer now fills its column. Early
  finish and download use one action in the Specification footer. A normal final Continue stores the
  completed Interview and reports that the specification is ready without an automatic compile or
  download. The output action downloads one portable `specification.zip` with the local fixture files.
  Review actions are disabled when their required Specification content is incomplete.

#### Deferred

- Source analysis, hosted state, authentication, and evaluation execution remain outside this
  change.

#### Breaking

- Rename the web client's `metricCatalogue`/`metricState`/`metricByFqn` state,
  `api.metrics()` call, and `Criterion.metric_fqn`/`metric_args` wire fields to
  `graderCatalogue`/`graderState`/`graderByFqn`, `api.graders()`, and
  `grader_fqn`/`grader_args`, matching the renamed `GET /api/v1/graders` route. The manual
  form's `scorer`-prefixed UI identifiers are unchanged — intentional, see
  `apps/web/AGENTS.md` (#415).
