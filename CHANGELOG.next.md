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

- Add the grader taxonomy vocabulary and authoring method. Define supported values as
  capabilities that a grader accepts and implements. Record that taxonomy groups can
  overlap and constrain each other, and that grader authors own the validity of
  declared combinations. Document Criterion Judge and DemoTraceBudget as working
  reference graders, with authoring steps and explicit limits on future capabilities.
  Align the glossary with Scope and its trace, subsession, and session attributes.

- Add the Docusaurus site setup, task-based navigation, shared page layout
  components, and METIS visual style. Include logo assets and Make commands
  to install, preview, check, and build the site. A `Pages` workflow checks the
  site on each pull request and publishes it to GitHub Pages from `main` when
  the repository is public. The landing page is served at `/metis/` and the
  documentation at `/metis/docs/`.

- Add the METIS landing page in `landing-page/`. It shows product screenshots of
  the Wizard, Engine, and Insights, a walkthrough of an evaluation, and links to
  the repository and the documentation. Use `make run-landing` to preview it and
  `make build-site` to build the landing page and the documentation together.

- Add the MIT licence and a security policy. The README shows the new logo, a
  centred title and description, and badges for the supported Python versions,
  the licence, and the project status. It also has sections for the project
  status, the maintainers and contact, and security reporting.

- **Defined Grading Scope in `GLOSSARY.md`.** The term names the part of a session that
  one grader result grades — the whole session, a trace, or an observation. It belongs
  to a result, not to a grader, and is distinct from the Baseline and Feature-specific
  scope qualifiers. A new Grading Scopes table defines Session, Trace, and Observation;
  Session and Trace move there from the main table, and Trace now states that its
  record is a group of observations. No code changes (#439).

- New user guide `docs/guide/models.md`: the LLM roles, recommended models, how to choose
  the user agent and judge models, variables, and Specification fields (#446).

#### Changed

- Use `AGENTS.md` as the agent instruction file. Remove the root and Wizard
  `CLAUDE.md` symlinks and update documentation and source references.

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

- `metis.core.target_binding.TargetBinding`: the YAML file a user writes to bind an app to
  the generic HTTP runner, published as `packages/core/schemas/target-binding.schema.json`
  (`schema_version` 1). It holds `identity`, `transport` (`http` only), `spec_url`,
  `tls_verify`, `auth`, `secret_headers`, `submissions`, `forbidden_calls`,
  `preflight_reads`, and an `advice` block (`limits`, `notes`) that is passed to the
  runner agent and not checked by code. Secrets appear only as environment-variable
  names, and validation error messages do not repeat a rejected value. `Specification` gains an
  optional `target_binding`, a path relative to `specification.yaml`. It is omitted when
  unset, so existing specifications and the wizard are unchanged. The engine does not
  read it yet; that is #481 (#478).

- `metis.core.trace_processing`: the shared trace processor for graders and the report. It
  gives turn and tool-call views of a session (`turns(traces)` takes the session's traces, so
  a caller that holds only traces needs no `GradingInput`); readers for plain text, OpenAI-style and
  OpenTelemetry GenAI messages, and tool arguments and results; `select_all`, `select_final` and
  `select_where`; `render_transcript`; and `find_artifacts`. Data it cannot read comes back as a
  `Problem`, kept apart from the target's own errors. That includes text holding a Langfuse
  media reference (`@@@langfuseMedia:…@@@`), since METIS does not fetch the media. `Observation` gains `level` and
  `status_message`, and `Trace.root` prefers a flagged root with no parent (#431).

- `Observation.raw` keeps the Langfuse row an observation was built from, and `SessionTraces` saves a
  session's traces as those rows, so a saved trace loses nothing that was fetched. `raw` is for saving,
  never for grading, and is left out of `model_dump` and `repr`. `execution_layout.TRACES` and
  `trace_file_name` name `outputs/traces/<session_id>.json` (#462).

- Preserve optional flat string metadata on Personas and Scenarios through
  Specification serialization. Accept arbitrary keys and reject non-string
  values, including nested objects and lists (#441).

- Shared ProductProfile, Experiment, and Specification models. The Profile holds product
  requirements. The Experiment holds Personas, Scenarios, Tasks, and execution settings.
  The Specification combines both in one document (#395).

- Publish one JSON schema for `specification.yaml` at
  `packages/core/schemas/specification.schema.json`. It requires `schema_version`, `id`, and
  `runner_factory_ref`, which every saved file carries. In-memory drafts still default them.
  The engine refuses a file without them (#465).

- All future shared file contracts belong in core. `make ci` checks published schema
  ownership, registration, and generated content (#465).

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

- **Choose the model and the gateway for each LLM role (#446).** New
  `metis.core.model_settings` has one role table: interview, embeddings, user agent, runner
  agent, and judge. Each role reads `<PREFIX>_MODEL`, `<PREFIX>_API_KEY`, and
  `<PREFIX>_BASE_URL`. The key and the URL each fall back to `OPENAI_API_KEY` and
  `OPENAI_BASE_URL`, and the runner agent first falls back to `USER_AGENT_*`, so a setup with
  one gateway does not change. `EMBEDDING_MODEL` replaces the hardcoded embedding model in
  the wizard and the testbed. `OPENAI_BASE_URL` is optional everywhere. Keys and URLs never go
  in a Specification, a `repr`, an error, or an API response.
  - One `DEFAULT_MODEL` variable sets the model of every chat role: Interview, user agent,
    runner agent, and judge. A role variable wins over it. When it is unset, the chat roles use
    `gpt-6-luna`, which is the one model name in the code. The embeddings role keeps its own
    default, `text-embedding-3-large`.
  - One `.env` search for `metis wizard`, `metis engine`, and the API: `METIS_ENV_FILE`, else
    the first `.env` from the working directory up to the project root. Exported values win.
    `metis-core` now depends on `python-dotenv`. One `.env.example` at the repository root
    lists the variables of every command. It replaces the `.env.example` files in
    `apps/api`, `packages/engine`, `packages/testbed`, and `packages/wizard`.
  - The Specification records the models that affect scores: `defaults.user_agent_model`,
    `defaults.runner_agent_model`, and `tasks[].user_agent_model`, beside
    `defaults.judge_model`. Precedence is the component, then the experiment default, then the
    environment, then `DEFAULT_MODEL`. Unset fields are not written, and
    `specification.schema.json` is regenerated. `TrialConfig` records `user_agent_model` and
    `runner_agent_model` for each trial.

#### Changed

- **`Artifact.at_turn` is now `at_simulated_turn`.** The number is the turn METIS's own
  simulation loop was on, counted from 1. It is not a position among the target's traces,
  because METIS cannot tell which trace produced a file. A saved `record.json` that still has
  an `at_turn` key loads, but the value is dropped and `at_simulated_turn` is `None`.

- **`TargetBinding` also binds a web page: `transport` is `http` or `browser` (#484).** A
  `browser` binding has a `start_url` and an optional `login` (`note`, the sign-in steps in
  plain words, and `secrets`, the environment variables it types), and `spec_url` is
  required only for `http`. Each transport rejects the other's fields: a browser binding sets
  none of `spec_url`, `tls_verify`, `auth`, `secret_headers`, `submissions`,
  `forbidden_calls` or `preflight_reads`, and an HTTP binding sets neither `start_url` nor
  `login`. Every existing HTTP binding stays valid, and `target-binding.schema.json` is
  regenerated. The published schema cannot express the per-transport rule, so only the
  model and the engine loader enforce it.

- `TargetBinding` requires each `{{secret:NAME}}` placeholder in `login.note` to name a
  variable in `login.secrets`. The error never repeats a placeholder that is not a variable
  name (#283).

- `GraderResult` and `RecordedResult` carry `scope`, the label of what the result is about
  (`"session"`, `"turn:3"` or `"artifact:report.pdf"`). `GraderRecord.aggregation` records
  the grader's aggregation rule (`"pass_if_all"`), or is omitted when the grader declares no
  taxonomy.

- `select_by_turn`, `select_by_window`, `select_session` and `select_by_artifact` in
  `metis.core.trace_processing` select what a grader judges for each scope, each under a
  label for `GraderResult.scope`. A trace is one turn on its own; a subsession is a turn and up
  to `window` turns before it, or every turn before it when `window` is not set. The artifact
  scope judges the latest revision of a named file: the highest `at_simulated_turn`, then the last one
  listed. `find_fixtures` gives the files the user gave the target, and `tools_offered` the
  tools the session offered, by agent, from the model calls, the agents and the tool calls.
  `render_artifact` gives a file in the form the judge reads, up to 50 MB.
  `GradingOutput.errored(reason)` builds the one result of a session that cannot be judged.

- `render_session` shows everything the trace records in each turn, in time order: the user's
  message, each agent's system prompt (once), what each model call wrote (never its input,
  which repeats the history), sub-agent handoffs, tool calls, errors and warnings at the
  observation where they happened, and the reply. `Turn.events` holds these events. With
  `tool_results=True` it adds each tool call's status (`ok`, `warning` or `error`) and result,
  including a result that is a list, and `max_chars` cuts long payloads. A JSON reply, tool
  argument or tool result is shown as the text the application recorded, so `10.50` stays
  `10.50`; `Observation.raw` is read only by the trace processor, for this. `render_dialogue`
  shows only what the user and the agent said to each other.

#### Breaking

- Each Criterion states one assessment rule and owns its Grader configuration (#490).

- Target and TargetProfile replace Product and ProductProfile. Specifications
  use the `target` key across Python, YAML, and API JSON (#429).

- Tasks use `behaviour_refs` to select measured Behaviours. Execution requires each selected Behaviour to have Criteria and evaluates all of them. Criterion score identity stays unchanged (#413).

- Rename `Criterion.metric_fqn`/`metric_args` to `grader_fqn`/`grader_args`, matching
  `GLOSSARY.md`'s **Grader** term for the concept these fields reference (#415).

### metis-library

#### Added

- **Taxonomy dimensions.** `metis.library.taxonomy` adds the `Dimension` enum and the
  `MEASURE_DIMENSIONS` table. The table gives the Dimension of each Measure, such as
  `error_recovery` in `execution_and_decision_quality` (#602).

- Fifteen Execution and Decision Quality graders: `PlanningQualityGrader`,
  `ActionChoiceAppropriatenessGrader`, `ToolChoiceAppropriatenessGrader`,
  `ToolArgumentCorrectnessGrader`, `StateTrackingGrader`, `UseOfPriorInformationGrader`,
  `ErrorDetectionGrader`, `ErrorRecoveryGrader`, `AdaptationToChangedConditionsGrader`,
  `StoppingAppropriatenessGrader`, `AvoidingUnproductiveRepetitionGrader`,
  `AppropriateHandlingOfCapabilityLimitsGrader`, `OutcomeVerificationGrader`,
  `ReasoningValidityGrader`, and `CoordinationQualityGrader`. Each judges the whole session.
  `task_description` is optional; without it the judge infers the goal from the user's
  messages. `ToolChoiceAppropriatenessGrader`, `ToolArgumentCorrectnessGrader`,
  `ActionChoiceAppropriatenessGrader` and `AppropriateHandlingOfCapabilityLimitsGrader` read
  the tool list from their `available_tools` setting, or else from the tools the session
  offered. `ToolArgumentCorrectnessGrader` needs recorded tool calls.
  `AvoidingUnproductiveRepetitionGrader` and `UseOfPriorInformationGrader` score a clean
  session 1 (#447).

- Eleven Task and Output Quality graders: `TaskSuccessGrader`, `OutputCorrectnessGrader`,
  `FactualAccuracyGrader`, `RequiredComponentCompletenessGrader`,
  `TaskConstraintAdherenceGrader`, `FormatSchemaComplianceGrader`,
  `ClaimSupportByEvidenceGrader`, `EvidenceSourceSuitabilityGrader`,
  `SpeechRecognitionAccuracyGrader`, `ContentFidelityGrader`, and `AttributionAccuracyGrader`.
  Output graders judge the final reply by default (`turn: last`), or every reply
  (`turn: each`), or the latest received file with a given name (`scope: artifact`,
  `artifact: <name>`). The judge reads the file itself. `ContentFidelityGrader`,
  `ClaimSupportByEvidenceGrader` and `AttributionAccuracyGrader` take their sources from the
  session: what the user gave the agent or what it retrieved, earlier turns, and the files
  the user gave the target. With a file, `TaskSuccessGrader` and
  `TaskConstraintAdherenceGrader` judge the file alone, and `TaskSuccessGrader` needs a
  `task_description` or `success_conditions`. `RequiredComponentCompletenessGrader`,
  `TaskConstraintAdherenceGrader` and `EvidenceSourceSuitabilityGrader` judge each listed
  item on its own and combine the results by `pass_if_all`: a result scores 0 when any listed
  item fails, is errored when none fails but one cannot be judged, and scores 1 otherwise.
  `FormatSchemaComplianceGrader` checks JSON against a schema without a judge call, before
  any prose rules (#447).

- Twelve graders adapt their judge prompts from open-source evaluation prompts:
  - Arize Phoenix: `ToolChoiceAppropriatenessGrader` (tool selection),
    `ToolArgumentCorrectnessGrader` (tool invocation), and
    `RequiredComponentCompletenessGrader` (completeness, with MLflow completeness).
  - MLflow: `TaskConstraintAdherenceGrader` (guidelines) and `OutputCorrectnessGrader`
    (correctness).
  - DeepEval: `AttributionAccuracyGrader` (citation faithfulness), `TaskSuccessGrader` (task
    completion), `PlanningQualityGrader` (plan quality), `SpeechRecognitionAccuracyGrader`
    (transcription accuracy), `ClaimSupportByEvidenceGrader` (faithfulness claims, with the
    Braintrust Autoevals faithfulness verdict), and `UseOfPriorInformationGrader` (knowledge
    retention, with MLflow knowledge retention).
  - Braintrust Autoevals: `FactualAccuracyGrader` (factuality, itself from the OpenAI Evals
    `fact` prompt).

  Each keeps the METIS binary score and the rule that a criterion that does not apply is not
  scored. `RequiredComponentCompletenessGrader` counts a refusal or "I don't know" as a missing
  component. Each module docstring
  names the source file, the pinned commit, the license and the METIS changes, and
  `metis/library/EXTERNAL_SOURCES.md` gives the copyright notices and license texts.
  `metis/library/graders/README.md` lists every grader with the upstream metric that it
  adapts.

- The taxonomy keeps Use of Observed State, Spoken-Content Fidelity, Language Identification
  Accuracy and Input Interpretation Accuracy, but the library has no grader for them: a trace
  does not record the environment state, the delivered speech, the identified language, or the
  meaning the user intended.

- Nine Interaction Quality graders, one for each attribute that a text session can show:
  `RelevanceGrader`, `CommunicationClarityGrader`, `CrossTurnCoherenceGrader`,
  `ClarificationAppropriatenessGrader`, `UserCorrectionSupportGrader`,
  `ActionStatusTransparencyGrader`, `ExplanationUsefulnessGrader`,
  `ToneAppropriatenessGrader`, and `OutputNaturalnessGrader`. Each judges the whole session
  by default. Relevance, clarity, explanation usefulness, tone, and naturalness also take
  `scope: subsession`, one result for each turn, judged with the turns before it. Each
  judge reads only the evidence that its measure needs: the user messages and replies for
  clarity, coherence, and tone, the replies alone for naturalness, and each tool call's
  status and result for action status. Seven graders take optional free-text settings that
  give the judge facts the trace cannot show: `purpose` (relevance), `audience` (clarity),
  `confirm_before` and `question_limit` (clarification), `fixed_rules` (correction
  support), `disclosure_level` and `ui_status` (action status), `expected_tone` (tone), and
  `conventions` (naturalness) (#451).

- Three Interaction Quality graders adapt their judge prompts from open-source evaluation
  prompts: `RelevanceGrader` from DeepEval Turn Relevancy, the padding check of
  `CommunicationClarityGrader` from Arize Phoenix `conciseness`, and
  `UserCorrectionSupportGrader` from Arize Phoenix `user_friction`. Each module docstring
  names the source file, the pinned commit, the license and the METIS changes, and
  `metis/library/EXTERNAL_SOURCES.md` gives the copyright notices and license texts.
  `metis/library/graders/README.md` lists the nine graders under Interaction Quality (#451).

- Three Reliability and Robustness graders, one for each attribute that one recorded
  session can show:
  - `RobustnessToToolFailuresGrader` judges whether the agent still reaches the required
    result or an acceptable fallback when a tool response is malformed, missing, delayed, or
    erroneous. The judge sees each tool call's recorded status and its result text. By
    default it gives one result for each recorded turn that has a tool call, and `scope: session` gives
    one result for the session. A session with no tool calls is errored. The optional
    `acceptable_fallbacks` setting lists the fallbacks that count. Its prompt adapts the
    error-handling rules of the Arize Phoenix `tool_response_handling` prompt.
  - `LongTaskPerformanceStabilityGrader` judges the whole session in one call and checks
    whether the later recorded turns are worse than the earlier ones: lost progress, dropped
    instructions, or contradictions of earlier turns. A session with fewer than `min_turns`
    recorded turns (default 4) is errored.
  - `RobustnessToContextDegradationGrader` judges whether a reply still uses the evidence it
    needs when the context is long, noisy, incomplete, or stale, and whether it asks or
    abstains when indispensable evidence is missing. By default it gives one result for each
    recorded turn, judged with the recorded turns before it, and it also takes `scope: session`. The optional
    `degradation` setting tells the judge what makes the context harder and where the needed
    evidence is.

  `metis/library/graders/README.md` lists the three graders under Reliability and Robustness
  (#450).

- Shared definitions for grading: `SCOPE_DEFINITIONS` in `metis.library.scope` (trace,
  subsession, session and artifact), `JUDGMENT_FORM_DEFINITIONS` in `metis.library.judgment_form`
  (the `binary` instructions and reply model), and `AGGREGATION_DEFINITIONS` in
  `metis.library.aggregation` (`none_single_score`, `pass_if_all` and `pass_if_any`, which
  combine a multi-rule grader's per-rule results). `GraderArgs` has optional `scope`,
  `judgment_form` and `aggregation` settings; an unset one is the grader's first declared
  value, and a value the grader does not declare fails before the run. `TraceArgs`, `SubsessionArgs`,
  `ArtifactArgs` and `TaskArgs` hold the settings that several graders share, and a grader's
  args must include the ones for the scopes it declares. A grader whose session lacks the
  evidence its measure needs, or where the event it looks for did not happen, returns
  `errored` with the reason.

- `metis.library.judge.judge` judges one rendered piece of a session against one criterion:
  it builds the prompt from the grader's criteria and the shared definitions, and returns the
  judge's status, score and reason as one result. It sends the request through the Responses
  API, with a rendered file as an input file. A gateway or model that rejects a file type gives
  an errored result with its reason.

- Criterion fallback judge for interview criteria with no specific grader match. The judge
  uses the current criterion description, returns a binary session score, and records errored
  assessments separately. YAML description edits apply on the next run. Model and threshold
  settings survive description edits. The judge reads the session transcript, with every tool
  call's result. It does not read artifact files. Shared binary output instructions and response
  validation live in `metis.library.judgment_form`. No taxonomy fields are required by the
  base grader contract (#299).

- `CriterionJudgeArgs` marks a model-based grader that takes its instructions from the
  criterion description. `criterion_judge_args` adds the description as `criterion` and rejects a
  `criterion` key in the settings or a blank clause (#299).

- `JudgeArgs.max_input_tokens` limits the estimated size of one judge request, with a default
  of 128,000. `input_budget_error` returns an errored result for a larger request, so the
  grader makes no model call. An invalid limit logs a warning and uses the default (#299).

- Define the grader taxonomy in code with string enums for measures,
  scopes, grader types, reference types, judgment forms, and aggregation.
  Interaction scopes are trace, subsession, and session.
  `GraderTaxonomy` declares one measure or an explicit `None` for a catch-all
  grader. The other five groups each contain one or more supported values. A taxonomy
  definition can hold shared behavior for one taxonomy value. The binary judgment
  definition supplies shared instructions and validation. Criterion Judge demonstrates
  an LLM assessment with no measure mapping. DemoTraceBudget demonstrates a deterministic
  task-constraint check. Both return one binary session result and declare fixed
  capabilities. The taxonomy does not add generic method selection or runtime routing.

#### Changed

- No library grader returns `skipped`. A session with nothing to judge is `errored`, with the
  reason, and the binary judgment's `not_applicable` status becomes an errored result.

- The demo graders show the full grader pattern. Each declares a taxonomy and selects through
  `SCOPE_DEFINITIONS`. `DemoTaskCompletionGrader` (session) and `DemoAnswerHelpfulnessGrader`
  (subsession, with the turns before each turn) judge with `metis.library.judge.judge`.
  `DemoAnswerHelpfulnessGrader` takes `DemoAnswerHelpfulnessArgs`, with `turn` and `window`.

#### Breaking

- Grader redesign without DeepEval. Graders subclass `metis.library.grader.Grader[Args]`,
  declare their parameters as an `args_model` (`GraderArgs`, or `JudgeArgs` for model-based
  graders), and implement `async grade(input, llm) -> GradingOutput` over the session's
  Langfuse traces and artifacts only. Every previous grader, the `MetisTurnGrader`/
  `MetisSessionGrader` bases, the GEval judge helpers and the `CriterionGEvalGrader` fallback
  are removed, and `deepeval` is no longer a dependency. The catalogue ships one grader,
  `TraceBudgetGrader` (`max_traces`), replacing `TurnBudgetGrader` (`max_turns`) (#415, #428).

- `TraceBudgetGrader` is now `metis.library.graders.demo.DemoTraceBudgetGrader`, beside three
  new demo graders (`DemoRequiredToolGrader`, `DemoAnswerHelpfulnessGrader`,
  `DemoTaskCompletionGrader`) that show how to read traces through
  `metis.core.trace_processing`. The demos are not re-exported from `metis.library.graders`,
  which exports no graders until real ones arrive. The placeholder `DemoMetric` is removed
  (#431).

### metis-engine

#### Added

- **The engine traces its own model calls to the METIS-internal Langfuse (#162).** When
  `METIS_INTERNAL_LANGFUSE_PUBLIC_KEY`, `METIS_INTERNAL_LANGFUSE_SECRET_KEY` and
  `METIS_INTERNAL_LANGFUSE_BASE_URL` are all set, `metis engine simulate` and
  `metis engine evaluate` record the prompt, the raw reply, the model, the token counts and the
  latency of each call. Each trial attempt is one trace, named `<task> x <persona> #<trial>`.
  It holds the user agent, artifact summarizer and runner agent calls, with the experiment,
  scenario, task, persona, trial and attempt as metadata. Each grader run is one trace, named
  by its criterion, that holds the judge calls of the grader. Its output is the status, score
  and reason of each result, so a code grader's trace shows its decision too. A trial's simulation and grading
  traces share one Langfuse session, `<experiment folder>/<task>/<persona>/<trial>`. The
  fixture summaries of gen_1 are one trace in the session of the experiment folder. Tracing is
  off when a variable is missing. The engine never traces to the `LANGFUSE_*` project, which
  it reads the target's traces from. Simulation and grading results do not change when
  tracing is off or Langfuse is unreachable. `metis-engine` now requires `langfuse>=3.0,<4.0`.
  `metis.core.model_settings.METIS_INTERNAL_LANGFUSE_VARS` names the three variables for the
  wizard and the engine.

- **The simulated user receives persona and scenario metadata (#442).** The gen_1 and gen_2
  user agents add each `metadata` entry to the persona or scenario description in the system
  prompt, as a `- key: value` line with the key as written. The Engine reads no key as a
  setting. For example, `start_prompt` and `stop_condition` only give the simulated user
  context. A persona or scenario without metadata gives the same prompt as before. The engine
  now uses the core `Persona`, so `metis.engine.simulation.types.Persona` requires `name`.

- **`fetch_session` rejects traces recorded before the Langfuse server's v4 upgrade.** Such a
  trace comes back from the v2 observations API with every observation duplicated and an extra
  root with id `t-<traceId>`, and its stored set changes with page size, so METIS does not try to
  repair it. `fetch_session` raises the new `UnsupportedTraceError` when a trace has that root or
  any repeated observation id. `metis engine evaluate` marks the session failed with a message
  naming the session and trace, then grades the remaining sessions. Re-run the trial to grade the
  session (#469).

- **Every simulation LLM call is logged, one row per request (#476).** `gen_1`'s user agent
  and artifact summarizer call through the shared `metis.engine.simulation.llm_calls`
  wrapper, which writes `at`, `component`, `requested_model`, `returned_model`, `tokens_in`,
  `tokens_out`, `latency_ms` and `error` as JSONL. A trial's calls go to
  `outputs/trials/<id>/evidence/llm_calls.jsonl`; the fixture descriptions summarized once
  per experiment go to `logs/llm_calls.jsonl`. A count the endpoint did not report is `null`,
  never `0`. The wrapper, not the OpenAI SDK, now retries a failed request (twice, on the
  SDK's rules: connection errors, timeouts, 408, 409, 429 and 5xx), so each attempt is its
  own row. When a trial is retried, the earlier attempt's file is kept as
  `llm_calls-superseded-<UTC timestamp>.jsonl` beside the new one. The row model is private
  to the engine. The user agent no longer writes its debug-level token-usage line, since the
  log carries those counts.
- **A transport log of every request and response, for the `gen_2` runners (#477).** The
  shared `metis.engine.simulation.transport_log` module writes
  `outputs/trials/<id>/evidence/log.jsonl`, one JSON line per entry: an ID, time, kind
  (`request` or `response`), role (`action` or `result`), the request a response answers, a
  one-line summary written by code, the headers and the body. `LoggingTransport` wraps an
  `httpx` transport, so every attempt is its own pair of entries, retries included.
  `Authorization` and every header a target binding lists under `secret_headers` are written
  as `***`, in requests and responses alike; the summary leaves the query string out. A body
  over 64 KB goes to `evidence/<id>.bin`, and a body that is a downloaded artifact is an
  `ArtifactRef` (the file's path and SHA-256) rather than a second copy. When a trial is
  retried, the earlier attempt's log is kept as `log-superseded-<UTC timestamp>.jsonl`, with
  its `.bin` bodies moved into a folder of the same name. The entry model is private to the
  engine, and `gen_1` does not write this log.
- **One place to record a file, with code-computed file facts, for the `gen_2` runners
  (#479).** The shared `metis.engine.simulation.artifacts` module records METIS's own
  `Artifact`, unchanged. `ArtifactLedger.record_download` saves a file under the last
  component of the target's name in `outputs/trials/<id>/artifacts/`, through a `.part` file
  that is renamed only once the bytes are whole, so a partial download is never kept. A name
  that is taken becomes `name-1.ext`, `name-2.ext`, and no saved file or entry is ever
  overwritten. Code sets `path`, `digest` and `state`, and the caller supplies `at_simulated_turn`. It
  returns the `ArtifactRef` the transport log uses. A download is refused, leaving no file
  and no entry, when a `.png`, `.jpg`, `.gif`, `.pdf`, `.docx`, `.xlsx`, `.pptx` or `.zip`
  does not start with its type's signature, or when a JSON document or JSON content type is
  saved under a name that is not `.json`; a chat reply saved as `.docx` is the case it was
  built for. A fixture has one entry however often it is uploaded, with the first upload's
  turn on it. Each entry's `content_description` is one facts line written by code, never the
  file's content: name, type and size, and for a CSV its data rows, columns and header,
  computed once per digest. `gen_1` does not use it.
- **Evidence pointers into the transport log, for the `gen_2` runners (#508).** A runner
  agent never states a fact for the record; it points at a logged response and code copies
  the value. `TransportLog.get` returns one entry by ID and `TransportLog.body_bytes` returns
  its raw bytes, whether the body is inline, in `evidence/<id>.bin` or an `ArtifactRef`; an
  artifact whose file no longer matches its recorded SHA-256 is refused. In
  `metis.engine.simulation.gen_2.evidence`, a `Pointer` is an entry ID, an optional path into
  its JSON body (`$`, `.key`, `["key"]` and `[n]`, no wildcards) and an optional regular
  expression applied to the text, which yields its one group or else the whole match. With no
  path the value is the body as text. `resolve` accepts only a `result` entry, so the agent
  cannot cite its own request, and only an entry in `allowed` when that set is given. Every
  refusal is a `PointerError` with a message the agent can act on. No tool uses it yet.
- **The generic HTTP runner's `http_request` tool and the rules code enforces on it (#509).**
  `HttpRunner.http_request` takes a method, an absolute `path` as the specification writes it
  (refused with `//`, a `..` segment or no leading `/`), a query, a JSON or multipart body and
  extra headers; the agent can never set `Authorization`, `Cookie` or `Host`. Code refuses a call
  matching the binding's `forbidden_calls` before sending it, adds `auth` and `secret_headers`
  (a header whose variable is unset is left out), and resends a 429 after its `Retry-After`, up
  to three times and never beyond the trial's remaining time. The specification is fetched once
  per trial and logged; the server is its first `servers` entry resolved against `spec_url`, and
  the entry is not one a pointer may cite. The user agent's `⟦…⟧` spans are numbered `{{1}}`,
  `{{2}}` for the runner agent, and code substitutes the exact text; a placeholder naming no span
  is refused. A submission (a call matching `submissions`, else any `POST`, `PUT` or `PATCH`
  with a JSON body) is refused when the action quoted nothing or another is still open; the
  runner exposes the open one and the responses that answered a submission, and takes the
  session ID from such a response or from a result logged during the current action, so a
  target that opens its session before any message (the toy app's `POST /sessions`) can have
  its ID recorded (#543). While a submission is open, the runner
  agent's `report` must set `submission` to `answered` (the reply is in the response it read) or
  `pending` (it comes later); `answered` closes the submission (`HttpRunner.settle_answered`),
  and code refuses it for a 202, whose reply comes later and settles through `poll_until`
  (#587, #593). `reply_from` only supplies the reply text: a path the response does not hold
  costs the reply, not the submission, and the notice says the target answered but no reply was
  recorded. The agent is shown each response body whole, with no length cap, so it reads the
  field it cites from the real response. A 405 during a poll is the runner's own wrong method on
  that path, so it leaves the submission open and is not reported as a submission that never
  settled; other 4xx answers still are (#593).
  A submission the target answers with a non-2xx status is never opened, and the user agent is
  told so: `Observation.notice` carries the status and the first 200 characters of the response
  body, copied from the transport log, and the orchestrator's per-turn log line shows the notice
  beside `reply`. The user agent's prompt says an error status need not be the assistant's fault (#545).
  An action whose runner tried to submit or type but was refused because the action quoted no
  `⟦…⟧` message sets `Observation.sent_nothing` (code decides it, never the runner agent) and
  a notice saying so. Reads the runner agent made first, such as a health check or opening the
  session, do not change that. It is not a turn: the orchestrator leaves it out of `total_turns`
  and the `max_turns` budget, the user agent is shown the notice, and three such actions in a row
  end the trial as a `system_error` with failure source `user_agent` and message
  `no_message_quoted`. Every field of the user agent's output now carries a description in the
  schema the model fills, and the `action` one says that the whole message goes between `⟦` and
  `⟧` and that an action without one sends nothing. An action that quoted nothing but never tried
  to send, such as a file fetch, is counted as before (#544).
  The per-trial text log and the TUI tail now show each event's own fields as `key=value` after
  the event name (the file's name, level and time are not repeated; the tail clips a long line).
  Each gen_2 line names who wrote it and carries the turn it belongs to: `user_agent_decided`
  holds the whole action and reasoning; `runner_agent_round` and `runner_agent_tool_call` (tool,
  result `ok`, `refused` or `transport_failed`, and a short detail, so a refused submission shows
  its reason) carry `turn=N`, or `turn=closing` for the closing call and `turn=sign_in` for the
  browser sign-in; `orchestrator_turn_result` closes each turn with the whole action and reply
  and the `counted` and `sent_nothing` facts.
  `HttpRunnerFactory.start` opens the HTTP transport
  (honouring `tls_verify`) and `close` closes it. A binding file that is not UTF-8 gives a clear
  `TargetBindingError`, and a `spec_url` with no host is rejected when the specification is
  fetched.

- **The generic HTTP runner's `poll_until` tool (#524).** `HttpRunner.poll_until(path, at,
  not_in=…, in_=…)` sends `GET path` every 5 seconds until the JSON value at `at` is no longer
  one of `not_in` (still waiting) or is one of `in_` (done); exactly one of the two is required.
  Code does the waiting, up to the trial's `response_wait_ms` and never beyond the trial deadline.
  When the condition holds, the open submission is cleared. A 4xx while a submission is open
  stops the poll, clears the submission and records it, with the failing response, in
  `HttpRunner.unresolved`; a timeout leaves it open and says so; a 429 is waited out, as in
  `http_request`, and the poll carries on. A path missing from the body, or a body that is not
  JSON, stops the poll with the pointer's message. Every poll's response can be cited, and a
  `GET` the binding forbids is refused with the same message as in `http_request`, which now
  shares that check. `resume_poll()` repeats the last poll while a submission is open.

- **The generic HTTP runner's `fetch_files` tool (#525).** `HttpRunner.fetch_files(listing,
  id_key, name_key, download_path, where=None)` downloads the files in a logged listing: code
  copies each item's ID and name from it, sends one `GET` per file and records it with the
  shared byte check, at the runner's turn. It refuses a listing that is not an array, one that is
  not this conversation's (its entry answered no submission and its request path does not name
  the recorded session ID as a whole segment), one over 100 files, and a `download_path` that
  lacks exactly one `{id}` or that the binding forbids. It skips a file already held, the user's
  own upload, and an ID that is not a single path segment. A non-2xx download or bytes that
  fail the type check are recorded `unfetched` with the reason, and a listed file with no ID
  `unavailable`, through the new `ArtifactLedger.record_failure`. `http_request` takes an optional
  `file_id_from` (a JSON path into a one-file upload's response) and passes the ID to
  `ArtifactLedger.record_upload(external_id=)`, which is how the user's upload is told from the
  target's files.

- **The generic HTTP runner's agent loop and `act()` (#481).** `HttpRunner.act` now carries
  out an action: it settles an open submission, then asks the runner agent
  (`RUNNER_AGENT_MODEL`, through `create_completion`, logged as component `runner_agent`) for
  tool calls until it calls `report`, at most 12 rounds and never past `response_wait_ms` plus
  60 seconds or the trial deadline. The agent's tools are `http_request`, `poll_until`,
  `fetch_files`, `session_id_from`, `note` and `report`; a refusal, a bad pointer or an argument
  that is not a JSON object goes back to the agent as `{"error": "refused, nothing was sent:
  …"}`. `note` keeps what the agent learned for later actions of the trial. Code builds the
  `Observation`: `reply` and `promised` are copied from entries logged during this action (a
  promised name must be a single line), the agent's `outcome`, `why` and `next_options` stay
  apart in `Reading`, `observed` is `False` while a submission is open or a call failed at the
  transport, and `notice` reports a failed poll, an open submission, a transport failure, the
  time limit or the round cap. An LLM failure raises `TurnRecoverableError`.
  `HttpRunnerFactory` takes an optional `llm` client and otherwise builds one from
  `OPENAI_API_KEY` and `OPENAI_BASE_URL`. `examples/gen_2-http-orca_api-1/orca-api.yaml` is an
  example target binding for Orca's API, and `simulation/gen_2/README.md` explains how
  `gen_2` works, the rules code enforces and how to write a binding for a new app. The runner
  has been tried on Orca's API only.

- **The generic HTTP runner's closing step, and checks that catch a trial METIS broke
  (#483).** `HttpRunner.end_chat` now runs the runner agent's loop with a closing
  instruction written by code and no user action: collect what the target made available
  that the file list lacks, reading the session's file list and calling `fetch_files` if
  the target has one, and send no message. It is not a turn, and the files it fetches are
  recorded under the last turn's number. Every promise still not `received` is then
  recorded `unavailable` ("promised in turn N, never delivered"). `Orchestrator` now
  treats only `received` and `unavailable` files as settled, so an `unfetched` file stays
  promised and is retried. Two checks fail a trial with `stop_reason` `system_error`,
  `failure_source` `evaluation_runner` and a `failure_message`, which the report already
  shows: `fixture_never_uploaded: <name>`, for a scenario fixture that was never sent,
  checked after the closing step on any trial that ran a turn and was not `interrupted`
  (including one that said `goal_achieved`); and `submission_unresolved`, which ends the
  loop at once when a reply never settles, and still runs the closing step.
  `Observation` gains `submission_unresolved` (default `False`), set by `HttpRunner`.

- **A generic browser runner, for an app with only a web page (#484).**
  `metis.engine.simulation.gen_2.runners.browser.BrowserRunnerFactory` binds an app with a
  `transport: browser` target binding. It launches headless Chromium once, and if the binding
  has a `login` the runner agent signs in once in `start()`; code types each
  `{{secret:NAME}}` (a name the binding lists, typed alone) and the logs show `***`. The
  logged-in state stays in memory, and each trial starts a context from it. The agent sees
  the page as an accessibility snapshot and acts through `snapshot`, `click`, `type`,
  `choose`, `choose_file`, `wait_for` and `fetch_files`, by element `ref`. Code refuses a
  choice the user did not name and any text typed when the action quoted none; a message is
  sent when its text leaves the field, and the submission stays open until `wait_for` settles
  it. Each action is logged as a `request` and each page capture, `{url, title, snapshot}`,
  as a `response`, so `report` can cite an element of a capture: `Pointer` gains `ref`. Files
  go through the ledger: downloads with `record_download`, and an upload only when the page
  then shows the file's name. `end_chat` does nothing for a browser. `run_tool` takes an
  optional table of handlers, which the browser runner uses to share `note`, `report` and
  `session_id_from`; the HTTP runner is unchanged. `load_target_binding` takes the transport
  the caller needs and refuses the other. `example-experiment/targets/web-chat.yaml` is an
  example, and `simulation/gen_2/README.md` has a section on it. **The runner has never met
  a live page:** it is tested on a fake page and on a static page in headless Chromium, its
  loop is a copy of `HttpRunner`'s to be merged with it in stage 4, and `orca_playwright`
  stays the runner for Orca's UI.

- **The generic HTTP runner's agent sends only what each round needs (#482).** The first
  message lists the target's operations as `METHOD path - summary` lines instead of the whole
  specification, and a new tool, `operation(method, path)`, returns one operation's definition
  from the parsed specification: local `$ref` links are followed three links deep and the
  result is cut at 6,000 characters, saying so. It makes no HTTP call and adds nothing to
  `results`, so it cannot be cited as evidence; an unknown operation is refused with the close
  paths, or the methods that path has. A specification that lists no operations is sent
  whole, as before, and `operation` refuses on it. Before each round, the body of every earlier
  `http_request` and `poll_until` result is replaced by `(logged as e7, 1,830 characters)`,
  and an earlier `operation` definition by a note to call `operation` again; the latest round,
  errors, statuses and entry IDs stay whole, and the full conversation is unchanged, so
  `report` can still cite any entry. Each round logs the characters it sends at debug level
  (`runner_agent_round`, field `chars_sent`). The agent's tools are now seven. YAML
  specifications are still not supported.

- **`gen_2`'s interface, user agent and turn loop (#480).** A runner factory that sets
  `generation = "gen_2"` now runs on `metis.engine.simulation.gen_2`. Its `Runner` has
  `setup(config)`, `act(action, promised) -> Observation`, `end_chat(promised)` and
  `teardown()`, and a `session_id` property for the ID code recorded. The `Observation` keeps
  the target's reply as code copied it apart from the runner's `Reading`, and the user agent
  is told the reading is an interpretation. The user agent states one plain-language action
  per turn, with the text for the target between `⟦` and `⟧`. Its prompt holds the persona and
  scenario descriptions and no knowledge of any target. Each file the user holds is its
  `file_facts` line and never its content, and files the target promised but has not
  delivered are listed. Its calls go through `parse_completion` into the trial's LLM-call log.
  The turn loop uses `gen_1`'s stop reasons and numbers `at_simulated_turn` from 1. Each turn updates
  the progress display, and a set `shutdown_event` ends the trial as `interrupted`. After the
  last turn it calls `end_chat` once. That call is not a turn and is not in `total_turns`.
  Errors behave as in `gen_1`, so the retry loop's partial record keeps the turns, artifacts
  and session ID so far. The record is the same `TrialRecord`, with one artifact per fixture.
  `gen_2` describes fixtures with `file_facts`, so no LLM call is made for them, and an
  author-supplied description still wins. Nothing in `gen_2` imports from `gen_1`. The seam
  now lists `'gen_1', 'gen_2'` as supported generations. There is no real `gen_2` runner yet.
- **The generic HTTP runner's factory, binding loader and runner-agent LLM calls (#507).** A
  runner factory may define `from_specification(specification, inputs_dir)`, and
  `metis engine simulate` then builds it with the specification instead of with no
  arguments. `HttpRunnerFactory` (`metis.engine.simulation.gen_2.runners.http`) does this to
  load the specification's `target_binding` from the experiment's `inputs/`; a binding
  outside the input folder is refused. `${NAME}` references in `spec_url` are expanded from
  the environment, and a relative `spec_url` is a file beside the binding. The
  `auth.secret_env` credential is required, and a secret header whose variable is unset is
  left out with a warning. Errors name a missing variable but never contain a value read
  from the environment. Its runner does nothing yet (#481). `llm_calls` gains
  `create_completion` for tool-calling requests, logged and retried as `parse_completion`
  is, and the runner agent's model is `RUNNER_AGENT_MODEL`, falling back to
  `USER_AGENT_MODEL`.

- **Each engine command checks and names its models before its first model call (#446).**
  `engine simulate` checks the user agent and, for a generic runner, the runner agent;
  `engine run` adds the judge, and `engine evaluate` checks the judge, when a criterion uses a
  model-based grader. The error names the variables, the `.env` path that was read, and
  `docs/guide/models.md`. When the keys exist, each command prints the models that it uses and
  where each comes from. The simulation models resolve when the engine builds each trial, not
  at import time.

#### Fixed

- A gen_2 trial is retried when the user agent's LLM stays unreachable. After the call's own
  retries run out on a connection error, a timeout, a 408, 409 or 429, or a 5xx, the user agent
  raises `UserAgentUnavailableError`, a `TrialRecoverableError`. The orchestrator lets it
  propagate, so the experiment replays the trial within its attempt budget, records the failure
  in `prior_failures`, and on the last attempt keeps the partial record with the turns played.
  A failure that cannot pass, such as a rejected key or request, a refusal or an unparseable
  answer, still ends the trial as a `system_error` without a retry (#401).

#### Changed

- **`run-manifest.json` names each file's turn `at_simulated_turn`** (was `at_turn`), after the
  `Artifact` field it comes from. See `metis-core`.

- **`metis engine simulate`/`run` default `--concurrency` to `1`.** Omitting the flag now runs
  trials sequentially instead of with 5 parallel workers.

- **`packages/engine/examples/` holds only the `gen_1-orca_api-1/` example.** The complete Orca
  specification, its fixtures, and the sample report are removed from it: the specification and
  the four CSV fixtures are already kept with the Wizard testbed in
  `packages/testbed/wizard/cases/orca/outputs/` (#414).

- **`metis engine evaluate` saves each session's traces.** Right after a session is fetched, and
  before it is graded, the traces are written to `outputs/traces/<session_id>.json` as the Langfuse
  rows (`SessionTraces`), so `metis insights report` can show the conversation without Langfuse access.
  The folder is cleared at the start of each evaluation, a session with no traces gets no file, and a
  failed write warns without failing the record (#462).
- Build one grader per active Criterion from the specification snapshot and reuse it
  across sessions. Record Criterion IDs, configured grader paths, and resolved arguments (#490).

- `CriterionJudgeArgs` graders get `criterion` from the criterion description at run time. The
  engine carries the description on the optional `metis.core.trials.GraderRef.description`
  field. A `criterion` key under `grader_args` is a pre-run setup error.
  `JUDGE_MAX_INPUT_TOKENS` sets the run default for `max_input_tokens` when a criterion does not
  set it (#299).

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

- **Moved today's user simulator into `metis.engine.simulation.gen_1`, behind a "run one
  trial" seam (#475).** The orchestrator, user agent, artifact summarizer, runner contract
  checks, the `Runner` ABC with its action and observation types, and the Orca API and
  Playwright runners now live under `simulation/gen_1/`; `RunnerFactory` lives in
  `simulation/factory.py`. The experiment's retry loop asks `simulation.trial.create_trial`
  for each attempt's trial. A runner factory may name its generation in an optional
  `generation` class attribute, and one without it runs on `gen_1`, so existing factories
  need no change. Behaviour is unchanged. `metis.engine.simulation.runner`,
  `metis.engine.simulation.types`, `metis.engine.simulation.runners.orca_api` and
  `metis.engine.simulation.runners.orca_playwright` still re-export their names, so
  existing `runner_factory_ref` values and the samples in `docs/guide/engine.md` keep
  working. The other moved modules are importable only at their `gen_1` paths, and their
  log lines show `gen_1` in the logger name.

#### Breaking

- Import `TrialRecord`, `TrialConfig`, `TrialOutcome`, `TrialFailure` and `GraderRef` from
  `metis.core.trials`; `metis.engine.simulation.types` no longer defines them (#423).

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
  removed (#417).

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

- The engine reads the one project `.env` (#446). It no longer reads `packages/engine/.env`
  or a `.env` above the project root. The `user_agent.config` and `runners.config` modules are
  removed; use `metis.engine.simulation.model_settings`. With no role variable and no
  `DEFAULT_MODEL`, the judge now uses `gpt-6-luna` (was `gemini-3.5-flash-lite`), and the user
  agent uses `gpt-6-luna` (was `gpt-5.6-luna`). A judge change changes scores. See
  `MIGRATION.md`.

### metis-insights

#### Added

- Report JSON includes 95% Wilson confidence intervals for each Task and Criterion,
  using passed and failed trial grades and excluding ungraded runs (#535).

- New package. `metis insights report --results-file <path>` reads an evaluation's
  `results.json`, prints the pass/fail/skip summary, and writes `report.json` and
  `report.html` into the same experiment's `reports/` directory (#417).

#### Changed

- Read recorded evaluation results in Insights. Preserve Criterion identity and run
  settings, and report grader errors separately from failed assessments. Report JSON
  and HTML use one plain Criterion description (#490).

- `metis insights report` reads `record.json` through `metis.core.trials.TrialRecord`. A record
  the model rejects is skipped with a warning. The trial's cause comes from
  `outcome.failure_source`/`failure_message`, then `stop_reason` and the trial's logs. The report
  no longer reads top-level `failure_source` or `error`, or `outcome.message`/`outcome.error`,
  which no engine writes, nor `conversation`, which #461 removed (#423).

- Reports read trial records from `outputs/trials/` and write `report.json` and
  `report.html` beside `outputs/reports/results.json` (#453).

- Each trial tab shows the conversation saved in `outputs/traces/<session_id>.json` (#503).

- Use Target in report JSON, failure sources, and report labels (#429).

- Expand Task Behaviour selections for plan counts, Criterion score attribution, and missing-result explanations (#413).

- `metis insights report` reads core `GraderRecord` results and writes terminal,
  JSON, and HTML reports. Each run uses the equal-weight mean of scored results and its
  recorded threshold. A criterion pools its runs. Behaviours, features, the headline, and
  persona and scenario rows take the unweighted mean of their evaluated children.
  Passed, failed, skipped, and errored counts appear beside every rate and mean score.
  The results table has one row per Task, and each trial tab shows that trial's result
  per criterion. The terminal summary adds errored counts and a mean score per criterion
  (#454).
  - The report rejects a `results.json` with `turn_results` or `session_results` and exits
    1. Re-run `metis engine evaluate`.
  - `report.json` keeps `schema_version: 1`. It adds `mean_score`, `judge_models`, and
    `error` counts, and it renames and removes other fields. The metis-engine section of
    `MIGRATION.md` lists the changes that a reader of the old file must make.
  - `report.json` adds `passRateTarget`, the 70% target below which the page shows a rate in
    red. It also adds each criterion's `name` and a `names` map of persona and scenario names.

- `report.html` is one page. It shows the average pass rate, the specification as a list or
  a tree with a detail panel, and a results table with each cell's pass rate and 95%
  interval. A click on a test case opens a panel with its trials, each criterion's 95% range
  against the 70% target, and each trial's conversation beside what each grader returned
  (#535).

- Reports write `schema_version: 1`. `metis.insights.Report` defaults a missing version to
  `1` and rejects other explicit versions. The published `report.schema.json` file is
  removed; report validation uses the `Report` model (#465).

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

#### Breaking

- The default embedding model is now `text-embedding-3-large` (was `gemini-embedding-2`).
  Set `EMBEDDING_MODEL=gemini-embedding-2` to keep existing embedding caches (#446).

### metis-wizard

#### Added

- **Grader taxonomy and settings in the catalogue.** `GraderSpec` and `GraderSummary` carry the
  grader's `taxonomy`. `GraderSummary` also carries the `dimension` of its measure. A grader with
  no taxonomy or no measure has `null` for these fields. Both models also carry `settings`, a
  list of `GraderSetting` values with the name, kind, required flag, default, choices, base flag,
  and description of each key that a Criterion can set. The list gives the `GraderArgs` settings
  `threshold`, `scope`, `judgment_form`, and `aggregation` first, then the grader's own settings.
  A taxonomy setting lists the values that the grader declares. The list omits `model`,
  `max_input_tokens`, and `criterion`, because the engine fills them. `GraderSummary` no longer
  has `default_args`. `GraderSpec.params` and the matcher do not change (#602).

- **Target connection with a gen_2 target binding.** At the start, the Wizard asks for **Build
  Spec only** or **Build Spec and Run Evals**. In run mode, the user selects HTTP API or Browser
  and enters the binding values. Secret fields take environment-variable names only. Every client
  validates the binding with `TargetBinding` and refuses a URL with a user name or password. The
  CLI also reports each named variable as set or not set and fetches the OpenAPI document or loads
  the start page and checks that the API server answers. The user can test again, fix the values,
  or continue. Run mode needs valid fields. A run-mode download has `outputs/target-binding.yaml`,
  and `specification.yaml` names the gen_2 runner and the binding. A spec-only download is the
  same as before. The connection travels in the optional `InterviewContext.connection` and in
  `InterviewStartRequest.connection`. Prompts and the model never read it. `metis wizard init`
  takes `--mode spec|run` and `--binding PATH`, and the new `metis wizard connect` command adds a
  binding later. In the web client, the mode is a toggle above the opening box, and run mode shows
  a Target connection card under the box. Send starts the Interview only with a valid binding. The
  completed Interview has a **Connect target** action. In the CLI, the mode is the first question.
  The API adds `POST /api/v1/wizard/connection/check` and `POST /api/v1/wizard/connection`. The
  check reaches the target only for an API that listens on this computer, and
  `METIS_API_CONNECTION_CHECK=1` or `0` overrides this. The API never expands a `${NAME}` variable
  into a URL that it requests, so a URL that names a variable is reported as not checked. `make
  run-api` listens on `127.0.0.1`. `init --mode run` with no terminal needs `--binding`. The
  API 422 response and binding errors never repeat an input value. `httpx` is a direct dependency
  (#283).

- **Run Evals from a manual Specification.** The run mode is now named **Build Spec and connect
  target**. The manual form keeps the mode that the user chose on the opening screen and shows the
  mode toggle at its top. In **Build Spec and connect target**, it shows the Target connection
  card with **Test connection** above the download. Each problem from the test shows under the
  field to fix. The form needs no model key and shows no model banner, and
  `POST /api/v1/wizard/connection/check` works when the API has no model key. The download needs
  a valid binding, and an invalid binding marks the card fields and stops the download. The run-mode
  download has `outputs/target-binding.yaml`, and `specification.yaml` names the gen_2 runner and
  the binding, the same as an Interview with the same binding. A spec-only manual download is the
  same as before. `package_specification` takes a `connection` keyword for a Specification source.
  `POST /api/v1/wizard/package` takes an optional `connection` form field with `specification`. It
  applies the `/connection/check` validation and gives 400 `validation_error` for an invalid
  binding or for `connection` with `state`. The error never repeats a binding value (#567).

- **Submission help from the OpenAPI document.** When the connection test reads the OpenAPI
  document, it suggests the `submissions` patterns for each write whose JSON body has exactly one
  required free-text field, and warns about each `submissions` pattern that matches no call in
  the document. `ConnectionCheckResult` has `suggested_submissions` and `warnings`. A warning does
  not make the binding invalid. The Wizard adds a suggestion to the binding only when the user
  accepts it: **Use these submissions** in the web client, or a yes in the CLI. The Engine infers
  nothing at run time. The call pattern rule is `call_matches` in `metis.core.target_binding`,
  so the Wizard and the Engine match patterns the same way (#606).

- The matcher selects `CriterionJudgeGrader` when no specific grader is similar enough, when
  the catalogue has no specific grader, or when the embedding provider fails. A rematch keeps
  the Criterion's settings when the selected grader does not change. Validation uses the
  current description. `GraderSummary.uses_criterion_description` marks graders that take
  their instructions from the description. The catalogue hides `criterion` and
  `max_input_tokens` from Criterion parameters (#299).

- Accept optional flat string metadata in model-proposed Persona and Scenario
  drafts and preserve it in saved Specifications. Guide generation to use supplied
  facts and omit unspecified metadata (#441).
- **Back on every Interview step.** Behaviours, Criteria, Personas, and Scenarios each show
  **← Back** in the CLI and the web client. Back from Behaviours opens a Target review form with
  the current name, users, description, and detail, and makes no model call. A changed
  description or detail asks the usual question about the current draft. With no change,
  Continue returns to the later step and drafts nothing again (#551).
- Support large supporting documents with shared limits of 500,000 characters per
  file and 1,000,000 total. Read YAML, JSON, and CSV text. Check the configured
  model context budget before each request without truncating input.

- **Keys in the CLI.** In an interactive terminal, every question is a list that the arrow keys
  move through, with a grey hint line that shows only the keys that the highlighted row accepts,
  separated by " | ". `init` starts with a welcome box, and each opening question has its own
  header. The opening questions are steps: Esc asks the question before again and keeps its
  answer. Each review is one grouped list with one row for each item. The keys select, open
  details, give feedback, go back, and continue: Space selects or clears a checkbox and sends
  only the changed rows, Enter with no changes continues, the right arrow opens closed details,
  and Tab moves to a feedback line under Back and Continue, with the list kept on the screen.
  Add, edit, and delete stay in the typed text menus and the web client. Test Cases draw as a
  table that fits the terminal width, and a narrow terminal shows each row on two lines. Forms
  use lists, and a choice that would repeat a used Persona and Scenario pair is unavailable. Esc
  cancels a form that can be cancelled. A warning that does not block is orange, and a blocking
  one is red. The working line is dim, with a blank line above it. A redirected run keeps the
  typed text menus. `prompt_toolkit` is a new dependency (#556).

- **Opening documents in the CLI.** `metis wizard init` accepts `--document PATH` (`-d`), once
  for each file. The CLI uses the same file types, limits, and extraction as the web client,
  and shows `Read`, `Not read`, or `Could not read` for each file before any model
  call. On a terminal, the user can keep a file that could not be read by name only. A run with no
  terminal stops with exit code 1. `init` keeps a copy of the files in `inputs/documents/`, and
  the export copies each file that a Test Case uses into `outputs/fixtures/`. The export removes
  the files that it copied before and that no Test Case uses now. When a Test Case uses a file
  that is not in `inputs/documents/`, the CLI shows `Add NAME to <out-dir>/outputs/fixtures before
  you run` (#554).

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

- **`metis wizard init` asks for the description.** `init` asks the package opening question in
  the terminal and asks again after an empty answer. The completed-export and
  Interview-in-progress checks run first, and the restart command in the in-progress error is
  `metis wizard init --out-dir <dir> --restart`. When stdin is not a terminal, `init` fails with a
  clear error and does not wait for input (#547).

- Interview opening now offers End user, Engineer, Compliance, and Security perspectives. The
  selected perspective travels in client-held Interview context and guides the language and depth
  of model responses, with specific guidance for Clarify and Behaviours. Labels and questions are
  package configuration. The web client asks for the perspective; the CLI always uses End user.

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
  explicit `name` and `description` fields;
  behaviour selection is `measured`; and Product uses `description`.

- **The wizard checks only the Interview key (#446).** `wizard init` and `resume` check the
  interview role before the first model call. The embeddings role is optional: without its
  key, the Wizard warns, and each Criterion uses the criterion judge. After it writes the
  files, the wizard CLI lists the roles that the run needs, with each model, its source, and
  how to change it.

#### Fixed

- **Interviews work with Azure OpenAI models (#614).** The structured-output schema lists every
  property as required, as Azure strict mode demands. A field that has a default accepts `null`,
  and the Wizard applies the default when the model sends `null`.

- Fix the type error when a new Interview creates its Specification. Preserve
  the initial Target details and Experiment defaults (#419).

- Retry Criterion drafts that leave measured Behaviours without Criteria, using
  the current Specification paths in the correction request (#444).

- **Required product details.** Before behaviour review, the Interview shows a form for any
  missing product name or description. The user can supply these details and continue when the
  model has not supplied them. Best-effort completion fills missing Target fields
  from the supplied evidence before it drafts the evaluation. Readiness validation
  still reports any remaining gaps. This form keeps the "Understanding your target" header,
  because it finishes that step. The "Features / Expected Behaviours" header comes with the
  review (#556).

#### Changed

- Configure Criterion descriptions and Grader arguments together during Wizard edits.
  Direct edits use typed fields and argument validation (#490).

- Refine Behaviour review with Feature groups, stable correction targets, a selected total, and
  separate Continue. Corrections and Target edits after Back update affected model content
  automatically and preserve form entries. Review options use one action set, `add`, `edit`, and
  `remove`, with the target ID naming the item. `Option.confirm` names the dependants that a
  deletion removes. `ChoiceRequest.sections` carries heading actions, `Card.profile_section_id`
  places each card, `FormChoice` dropdowns send IDs, and `FormRequest.submit_label` names the
  submit button. A Test Case is unique by its Persona and Scenario pair. Scenarios and Test
  Cases are separate steps (`InterviewStep.TEST_CASES`). The model drafts Scenarios only.
  Continue on Scenarios calls `draft_test_cases`, which picks the Personas and Behaviours for
  each Scenario with no Test Case, and each pick becomes a selected Test Case. A Behaviour that
  no selected Test Case covers shows as a gap on the Test Case review. `InterviewState.excluded_tasks` holds the Test Cases that the user cleared;
  readiness and the export use the selected ones only. `FormField.multiple`, `FormField.column`,
  `FormChoice.hint`, `Option.hint` and `Card.show_id` support in-place row edits and ID chips. Chat feedback can select
  Behaviours and set Trials. Back closes an open form and reopens the last review from a
  completed Interview. A change of the selected Behaviours after Back removes unselected Behaviours from Test Cases. `init` asks
  for a Perspective. Capability evidence and confidence can be omitted together.
  Prompts use the selected Perspective and available capability context throughout the Interview.
  Default generation budgets are five Behaviours and three Criteria per selected Behaviour,
  with expansion for explicit requests and required coverage (#353).

- The wizard offers no graders until real ones are added to `metis.library.graders`: the
  interview cannot produce a runnable experiment, and the manual form's grader picker is empty
  (#470).

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
  `args_model`. A `grader_fqn` that names an abstract `Grader` is a validation error (#428).

#### Removed

- **The wizard no longer serves its own HTTP door or frontend.** The stateful web server, the
  per-interview store, the `metis-wizard serve` command, the committed React bundle, and the wizard
  FastAPI, Uvicorn, and multipart dependencies are gone. A web client now talks to the new
  `metis-api` service over HTTP. The interview itself — models, driver, screens, compiler — does not
  change.
- **`InterviewStep.PRIORITISE` is removed**, with its screen, transitions, and status. The interview
  now shows five steps.

#### Breaking

- **Interview tracing uses the METIS-internal Langfuse.** The wizard and the API trace their model
  calls only when `METIS_INTERNAL_LANGFUSE_PUBLIC_KEY`, `METIS_INTERNAL_LANGFUSE_SECRET_KEY` and
  `METIS_INTERNAL_LANGFUSE_BASE_URL` are all set. They no longer read `LANGFUSE_*`, which stays the
  Langfuse of the system under test for `metis engine`. Before, one `.env` sent Interview prompts
  and replies to the target's project. To keep wizard tracing, copy the keys to the new
  variables (#578).

- Rename the wizard `Task` and `TaskDraft` models to `Feature` and `FeatureDraft`. Specifications use
  `features`, patch paths use `features[...]`, and new feature IDs use `F-`. Specification schema
  version 1, prompts, API types, browser forms, and reports use the glossary term (#392).

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

- The wizard reads the one project `.env` (#446). It no longer reads `packages/wizard/.env`.
  `configure_interview_runtime` takes resolved `interview` and `embeddings` role settings and
  no longer writes to `os.environ`. The default embedding model is now
  `text-embedding-3-large` (was `gemini-embedding-001`), so grader matches can change. With no
  `INTERVIEW_MODEL` and no `DEFAULT_MODEL`, the Interview uses `gpt-6-luna` (was
  `gpt-5.6-luna`). See `MIGRATION.md`.

### metis-api

#### Added

- **Grader taxonomy and settings rows.** Each `GET /api/v1/graders` row adds `taxonomy` and
  `dimension`, so a client can group and filter the graders. Each row also adds `settings`, with
  the required and optional settings of the grader and their kinds and defaults. The row no
  longer has `default_args`. Use the `default` of each setting in `settings` (#602).

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

- **Model status route (#446).** The API starts without model settings. New
  `GET /api/v1/models` returns the model, its source, the configured status, the score effect,
  and the missing variable names of each role. The runner agent model follows the user agent
  model, as in the engine. The Interview routes return 503 `model_unavailable` until the
  interview role is configured.

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

- The API reads the one project `.env` (#446). It no longer reads `apps/api/.env`. A health
  check no longer fails when a key is missing; check `GET /api/v1/models`. See `MIGRATION.md`.

### metis-web

#### Added

- **Grouped grader picker.** The manual form groups graders by dimension, such as Task and
  Output Quality and Interaction Quality. Graders with no dimension are in an Other group. Each
  row shows its grader types, scopes, reference types, and judgment forms as chips, with one
  colour for each field. The search also finds the measure, the chip values, and the dimension
  name. Each
  selected grader has a settings box with a description and one list of every grader setting:
  the common settings first, then the grader's own settings. Each setting starts from its default.
  A choice setting has a dropdown. A required setting has a red `*` after its name, and the download
  stops until it has a value. An empty value uses the grader default. The form has no custom
  setting keys. The form is more compact. The page has a Specification part and, in run mode,
  a separate Target connection part with a neutral card. Each section has a plain heading with a
  plus button, each Persona, Scenario, and test case card has a tinted header, and descriptions
  and lists sit side by side on wide screens. The download button has an icon and sits next to
  the mode picker in a bar that stays at the top while the form scrolls. A Persona card uses a
  pencil button to edit and a check button to finish. The download button is grey until every
  field is complete. A click on it still marks the fields to fix, and the form shows no
  separate "not complete" message. The grader search is the top row of the
  grader list box, and the list scrolls inside the box. The test case files are labelled
  "Fixtures (files the target can use in each trial)" (#602).

- The manual form omits graders that take their instructions from a criterion description,
  because the form has no criterion description (#299).

- **Manual metadata.** Personas and Scenarios have optional Metadata
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
  Persona and one Scenario, with its own Trials, graders, and files. The form retains
  assigned Task IDs and stores grader settings on Criteria. It builds `specification.zip`
  with `specification.yaml` and fixtures through the existing API, without an Interview
  record (#395). When a field is not complete, **Download specification** marks each
  field that needs a change, shows what to change, and moves the focus to the first one.

- **Model settings in the browser (#446).** Send is grey, with "Configure API keys to start
  interview", while the interview role is not configured. A missing embeddings key shows a
  banner. The run roles show only in the run settings step. That step comes after the last
  review and before the download, and it writes the model names into the Specification, so the
  first ZIP holds them. An empty runner agent field shows the model that the run uses: the
  typed user agent model, unless `RUNNER_AGENT_MODEL` is set.

#### Changed

- **Tighter layout and the METIS brand.** Padding, margins, and gaps are 10% smaller across the app,
  and body text has a line height of 1.5. The navigation rail shows the METIS mark and the METIS
  wordmark, the same as the docs site (#602).
- **Opening setup in the chat box.** The Perspective and capability controls are now in the bottom
  row of the opening box, next to the documents button. The separate capability screen and its
  **Edit target** button are removed. The Perspective control marks End user as the default until
  the user opens it. Its panel shows the question of each Perspective as text, so hover is not
  necessary. The **Capabilities** control opens the capabilities and the confidence in a panel
  under the box, or in a full-width sheet on a small screen. Each capability group is one column,
  so the panel needs no scroll. The capabilities and the confidence are optional. With no
  confidence, the web client sends Low. In the Perspective and confidence choices, the arrow keys
  move the selection and the focus. The opening has less text: the placeholder is an example
  description, the panels have no title, and the manual entry is one line (#555).

- Show Criterion descriptions with expandable Grader details and typed edit fields (#490).

- Make the Profile the main work area. The active review shows in its matching Profile section,
  and the chat keeps a feedback field open beside it with a placeholder for each step. Behaviour
  review has collapsible Feature groups, compact selection rows, a selected total, and corrections
  in place. Capabilities that the user does not open are sent as unspecified evidence. Every
  item has Create, Edit, and Delete: "+" on a heading, a pen, and a trash icon, with edits in
  place. Delete asks first and names the items that go with it. The Behaviour step is titled
  "Features / Expected Behaviours" and warns when more than five Behaviours are selected.
  Drag the line between the chat and the Profile to change the chat width. Section and group
  headings show no item counts.
  Criterion review retains Feature groups, with no checkboxes and with Grader details in quiet
  text. Its instruction says that the Criteria under a Behaviour show how well it performs. The Scenarios step shows a Scenario card list. The next step, Test Cases, shows a
  table with Persona, Scenario, Behaviours, Trials, and Files columns that edit in place. The Test Case checkbox
  includes it in the evaluation, and the total counts selected Test Cases only. Every step moves
  on with Continue. Back works while a form is open and from
  Run settings and the completed Interview (#353, #489).

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
  finish and download use one action in the Specification footer. If early finish requires a review,
  the conversation shows it and preserves it across reloads for confirmation before download.
  A normal final Continue stores the completed Interview and reports that the specification is ready
  without an automatic compile or download. The output action downloads one portable
  `specification.zip` with the local fixture files.
  Review actions are disabled when their required Specification content is incomplete.

#### Fixed

- **Opening panels with the target connection.** In **Build Spec and connect target**, the
  Perspective or Capabilities panel and the Target connection card are now stacked with a gap
  between them. Before, the connection card was drawn over the bottom of the open panel (#602).
- **A Test Case row is read-only until the pencil opens it (#584).** The row shows the selected
  Behaviour IDs, the Trials number, and the attached files, with no controls. A new Test Case has
  no files. The pencil makes the Behaviour chips clickable and the Trials editable. In edit mode,
  the Files cell has one **Add file** menu: **Upload a file** first, then the opening documents
  that are not attached yet.

#### Deferred

- Source analysis, hosted state, authentication, and evaluation execution remain outside this
  change.

#### Breaking

- Rename the web client's `metricCatalogue`/`metricState`/`metricByFqn` state,
  `api.metrics()` call, and `Criterion.metric_fqn`/`metric_args` wire fields to
  `graderCatalogue`/`graderState`/`graderByFqn`, `api.graders()`, and
  `grader_fqn`/`grader_args`, matching the renamed `GET /api/v1/graders` route (#415).
