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

- `pytest-asyncio` is a declared dev dependency; it was previously installed only through
  `deepeval` (#428).

### Docs

#### Added

- **Defined Grading Scope in `GLOSSARY.md`.** The term names the part of a session that
  one grader result grades — the whole session, a trace, or an observation. It belongs
  to a result, not to a grader, and is distinct from the Baseline and Feature-specific
  scope qualifiers. A new Grading Scopes table defines Session, Trace, and Observation;
  Session and Trace move there from the main table, and Trace now states that its
  record is a group of observations. No code changes (#439).

#### Changed

- Use Target for the evaluation subject in interface labels, prompts, code
  documentation, and guides (#429).

- **Clarified `GLOSSARY.md`'s Session definition.** A session now explicitly
  corresponds to exactly one trial: the target agentic system's conversation
  for a trial produces the traces that make up its session. This resolves an
  apparent naming overlap between `target_session_id`, the Langfuse
  session-grouping key, and `MetisSessionMetric` — they are the same concept
  once the one-to-one relationship with trial is stated. No code changes.
  ([#409](https://github.com/govtech-responsibleai/metis/issues/409))

### metis-core

#### Added

- Preserve optional flat string metadata on Personas and Scenarios through
  Specification serialization. Accept arbitrary keys and reject non-string
  values, including nested objects and lists (#441).

- Shared ProductProfile, Experiment, and Specification models. The Profile holds product
  requirements. The Experiment holds Personas, Scenarios, Tasks, and execution settings.
  The Specification combines both in one document (#395).

- `metis.core.traces`: `Observation`, `Trace` and `GradingInput`, the read-only input of every
  grader run. `Trace.root` finds the logical root observation by `isRootObservation`, falling
  back to the parentless observation only when the flag is absent from the whole trace (#428).

- `metis.core.grading`: `GraderResult`/`GradingOutput`, what a grader returns (a score per
  grading scope, or skipped/errored), and `RecordedResult`, its outcome after the threshold
  (#428).

- `metis.core.reporting`: `EvaluationResults`, the version-guarded `reports/results.json`
  holding one `GraderRecord` per grader per session that `metis-engine` writes (#417, #428).

- `metis.core.trials`: `TrialRecord`, the version-guarded `outputs/trials/<trial>/record.json`,
  with `TrialConfig`, `TrialOutcome`, `TrialFailure` and `GraderRef`, moved from `metis-engine`
  so `metis-insights` can read records through the same model. `TrialOutcome` has optional
  `failure_source` and `failure_message`, naming the cause of a failed trial (#423).

- `defaults.judge_model` in `specification.yaml`: the experiment's default judge model for
  model-based graders. It is omitted from the document when unset (#428).

#### Breaking

- Target and TargetProfile replace Product and ProductProfile. Specifications
  use the `target` key across Python, YAML, and API JSON (#429).

- Tasks use `behaviour_refs` to select measured Behaviours. Execution requires each selected Behaviour to have Criteria and evaluates all of them. Criterion score identity stays unchanged (#413).

- Rename `Criterion.metric_fqn`/`metric_args` to `grader_fqn`/`grader_args`, matching
  `GLOSSARY.md`'s **Grader** term for the concept these fields reference (#415).

### metis-library

#### Breaking

- Grader redesign without DeepEval. Graders subclass `metis.library.grader.Grader[Args]`,
  declare their parameters as an `args_model` (`GraderArgs`, or `JudgeArgs` for model-based
  graders), and implement `async grade(input, llm) -> GradingOutput` over the session's
  Langfuse traces and artifacts only. Every previous grader, the `MetisTurnGrader`/
  `MetisSessionGrader` bases, the GEval judge helpers and the `CriterionGEvalGrader` fallback
  are removed, and `deepeval` is no longer a dependency. The catalogue ships one grader,
  `TraceBudgetGrader` (`max_traces`), replacing `TurnBudgetGrader` (`max_turns`) (#415, #428).

### metis-engine

#### Changed

- Execution folders use `experiments/execute/<id>-<timestamp>/`, with trial records
  and artifacts in `outputs/trials/` and results in `outputs/reports/results.json`.
  Input snapshots and logs keep their names. Evaluation and resume use the execution
  root. Core owns the shared execution paths (#453).

- **Migrated the Langfuse trace extractor to the v2 observations endpoint.** The nprd Langfuse
  server moves to v4 `events_only` mode, which permanently 404s the v1 `GET
  /api/public/traces` and `GET /api/public/observations` endpoints `fetch_by_session_id` used.
  v4 has no standalone Trace entity — a trace's id/input/output/timestamp now come from its root
  observation, found by `isRootObservation`, falling back to the observation with no
  `parent_observation_id` only when the flag is absent from the whole trace. Fetching uses a two-step
  `observations_v_2.get_many` call per trace, not one call per session: a session-wide,
  `sessionId`-filtered call finds which traces exist (defensive against Orca's agent-run spans
  carrying a different session id — issue #435 — the root observation's session id is always
  correct, so this step is reliable), then each trace is re-fetched in full with a `traceId`
  filter, which never depends on any child observation's session label. This has the same shape
  as the superseded v1 `trace.list` + `observations.get_many` pair, with the second call now
  going through `observations_v_2.get_many` as well. Every trace in the session is kept,
  including traces whose root has no output; metadata that may have been truncated at 200
  characters is fetched again with every key expanded. A trace with zero or multiple root
  candidates falls back to the earliest `start_time` and logs a warning rather than crashing
  the evaluation run. No dual-endpoint fallback — the v1 calls are removed outright (#432, #435, #428).

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

- Import `TrialRecord`, `TrialConfig`, `TrialOutcome`, `TrialFailure` and `GraderRef` from
  `metis.core.trials`; `metis.engine.simulation.types` no longer defines them (#423).

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

- `metis engine evaluate` grades with the new contract. Each criterion's grader is built once
  from the specification snapshot and validated before the run (`grader_args` against its
  `args_model`, plus `check_setup`), then run once per session on every trace of the session.
  A score at or above the criterion's `threshold` (default 0.5) passes; empty, raising or
  mistyped grader output is recorded as errored, never failed. Judge credentials
  (`JUDGE_API_KEY`/`JUDGE_BASE_URL`, falling back to `OPENAI_*`) are required only when a
  criterion's grader is model-based; its model resolves from `grader_args.model`, then
  `defaults.judge_model`, then `JUDGE_MODEL`, then `gemini-3.5-flash-lite`, and is recorded
  in `grader_args`. `results.json` now holds one GraderRecord per grader per session
  (schema_version is unchanged). `fetch_by_session_id`,
  `FetchLangfuseResult`, `evaluate`, `EvalResult`, `RoutingSummary` and
  `DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE` are removed; use `fetch_session`,
  `build_criterion_grader` and `grade_session` (#428).

- The bundled full example experiment names a grader on one Criterion (`AC-EXEC-3`) and leaves
  the other 83 empty, so the engine refuses to run it until graders exist; the `simple`
  example runs end to end with `TraceBudgetGrader` (#428).

- `TrialRecord.conversation` is removed, along with the `ConversationTurn`, `TurnDiagnostics`
  and `ActionRetry` models, so `record.json` no longer holds a copy of the transcript. The
  conversation is read from the Langfuse session named by `target_session_id`.
  `TrialOutcome.total_turns` still counts completed exchanges. A `record.json` that still has a
  `conversation` key loads, with the key ignored (`schema_version` is unchanged). Per-turn detail
  that only METIS sees and Langfuse does not (the persona's UI actions, withheld or undelivered
  action rows, and `Observation.discarded_message`) is now only in the trial's `logs/`. The
  per-turn timing breakdown is dropped from the console summary printed after each trial, and
  `discarded_message` is now logged in full rather than cut to 80 characters. Until #462 lands,
  `metis insights report` shows no turns in the trial-trace view for new trials, failure messages
  fall back to outcome-level detail, and a failed trial that was blamed on the target because of
  per-turn error notices is now blamed on the evaluation runner unless its outcome names a
  source (#461).

### metis-insights

#### Added

- New package. `metis insights report --results-file <path>` reads an evaluation's
  `results.json`, prints the pass/fail/skip summary, and writes `report.json` and
  `report.html` into the same experiment's `reports/` directory. It owns `Report` and
  `report.schema.json`, and `make ci` checks that schema (#417).

#### Changed

- `metis insights report` reads `record.json` through `metis.core.trials.TrialRecord`. A record
  the model rejects is skipped with a warning. The trial's cause comes from
  `outcome.failure_source`/`failure_message`, then `stop_reason` and the trial's logs. The report
  no longer reads top-level `failure_source` or `error`, or `outcome.message`/`outcome.error`,
  which no engine writes, nor `conversation`, which #461 removed, so the trial-trace view stays
  empty until #462 (#423).

- Reports read trial records from `outputs/trials/` and write `report.json` and
  `report.html` beside `outputs/reports/results.json` (#453).

- Use Target in report JSON, failure sources, and report labels (#429).

- Expand Task Behaviour selections for plan counts, Criterion score attribution, and missing-result explanations (#413).

- `metis insights report` still reads `results.json` version 2 and rejects files from the
  current `metis engine evaluate` with "This results.json uses the new GraderRecord format
  (grader redesign #428), which metis insights report cannot read yet. Rerun the report once
  #454 is released."; its redesign is #454 (#428).

### metis-testbed

#### Added

- Add five reference cases for Orca, Enterprise AI Assistant, travel planning,
  billing support, and incident triage. Each case includes a reference
  Specification, source notes, and available fixtures. Add an offline reviewer
  with a Behaviour–Test Case matrix and YAML view. Keep the guide, cases, and
  reviewer together under `packages/testbed/wizard/`. Orca product inputs and
  generated previews stay local; the other case inputs are tracked (#436).

- Add a Wizard evaluation command that sends each case's `prompt.md` as the first
  Interview message and uploads its supporting documents. It scores generated
  Specifications at the Feature, Expected Behaviour, Criterion, Grader, and
  Task levels, saves results by Wizard version, and compares saved versions (#436).
  Record completion separately from scores, accept the final ready Scenario review,
  and retain structured failures with missing requirements and diagnostic state.
  Share embedding preparation between reference and generated Specifications, with
  local caches beside each YAML file. Add separate `embed` and `score` commands;
  scoring creates missing embeddings and reuses valid entries. Save score reports
  under `results/` and keep embedding caches beside the Specification YAML. Report behaviour
  mean nearest-neighbour similarity and pair details for behaviour text and
  feature–behaviour–criteria context,
  plus pair difference error when a reference is supplied.
  Include experimental reference and generated mean NN scores with Behaviour counts
  in the normal Wizard run summary and saved case results.
  Document commands, metrics, and example CLI tables in the Wizard suite README.

### metis-wizard

#### Added

- Accept optional flat string metadata in model-proposed Persona and Scenario
  drafts and preserve it in saved Specifications. Guide generation to use supplied
  facts and omit unspecified metadata (#441).
- Support large supporting documents with shared limits of 500,000 characters per
  file and 1,000,000 total. Read YAML, JSON, and CSV text. Check the configured
  model context budget before each request without truncating input.

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

- Fix the type error when a new Interview creates its Specification. Preserve
  the initial Target details and Experiment defaults (#419).

- Retry Criterion drafts that leave measured Behaviours without Criteria, using
  the current Specification paths in the correction request (#444).

- **Required product details.** Before behaviour review, the Interview shows a form for any
  missing product name or description. The user can supply these details and continue when the
  model has not supplied them. Best-effort completion fills missing Target fields
  from the supplied evidence before it drafts the evaluation. Readiness validation
  still reports any remaining gaps.

#### Changed

- Wizard exports use timestamped design folders with `inputs/` and `outputs/`. The default name is `YYYYMMDD-HHMMSS-interview`, using local 24-hour time. Manual ZIP exports use the `-manual` suffix. ZIP filenames match their root folders. Interview exports retain the final state used to compile the Specification. CLI recovery uses the completed Specification as its completion marker (#453).

- Use Target in Interview prompts, fields, patch paths, and validation codes (#429).

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

- The grader catalogue lists concrete `Grader` subclasses and their `args_model` fields
  (omitting a model-based grader's `model`), and `grader_args` are validated against
  `args_model`. The matcher's below-threshold fallback still names the removed
  `CriterionGEvalGrader`, so a Criterion it cannot match does not compile: the CLI and the API's
  `/compile` (HTTP 400) report "Criterion X: no grader matched and the fallback judge was removed
  in the grader redesign (#428); choose a grader for this criterion." A `grader_fqn` that names
  an abstract `Grader` is also a validation error (#428).

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

- Package exports accept either final Interview state or a manual Specification. ZIP files use the shared export layout and expose the Wizard-owned filename in `Content-Disposition`; manual exports include an empty `inputs/` folder (#453).

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

- **Manual metadata.** Personas and Scenarios have optional Additional context
  key/value fields. Export preserves the text values and checks for blank or
  duplicate keys (#441).

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

- Interview downloads send the final state for compilation and export. Interview and manual downloads use dated archive names and the shared `inputs/` and `outputs/` layout. The browser shows where to extract them (#453).

- Use Target in authoring views and upgrade saved Interviews while preserving
  user text, pending forms, and file bytes (#429).

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
