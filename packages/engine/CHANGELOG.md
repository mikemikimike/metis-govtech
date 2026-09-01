# Changelog

All notable changes to `metis-engine` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.12.0] — Unreleased

### Added

- `RunnerFactory` protocol in `simulation/runner.py` — abstracts shared-resource lifecycle and per-attempt runner creation.
- `simulation/_artifact_store.py` — runner-agnostic artifact manifest writer (moved from `runners/playwright/`).
- **Pluggable runner via `runner_factory_ref`** — required `runner_factory_ref` field in `experiment.yaml` accepts a fully-qualified RunnerFactory class name; validated at load time with a clear error if the FQN is unimportable or doesn't satisfy the RunnerFactory protocol.
- **User guide: "Adapting to Your Target System"** — new section in `docs/guide/engine.md` covering the Runner ABC, RunnerFactory protocol, a complete REST API runner example, `runner_factory_ref` wiring, `profile.yaml` schema reference, Langfuse requirements, and a minimal experiment template with pre-flight checklist.
- **Orca API runner** (`simulation/runners/orca_api/`) — drives simulations over Orca's key-authenticated REST API (`/api/v1`). Submits turns via `POST /chat`, polls digests, handles typed forms, uploads fixtures with experiment-scoped caching, and downloads generated artifacts. Includes rate limiting, backoff for transient failures, and turn cancellation on timeout.
- **Shared HTTP utilities** (`simulation/runners/_http.py`) — `SubmitRateLimiter`, `poll_until`, `send_with_backoff`, `download_to` for API-driven runners.
- **TLS verification bypass** — `insecure` flag in Orca API runner config (`config.yaml`) and `build_client()` for targets with self-signed certificates.
- **Configurable user-agent token budget** — `USER_AGENT_MAX_TOKENS` env var controls the max tokens for the simulation persona LLM; omitted by default so the provider's own limit applies. Set explicitly (e.g. 4096) for reasoning models where chain-of-thought tokens count against the limit.
- **`RunRetryConfig`** (`simulation/config.py`) — shared run-level retry budget model.
- New exception types: `TargetUnavailableError` (turn-recoverable), `TargetSessionLostError` (run-recoverable), `TargetSessionEnded` (clean session exhaustion → `target_exhausted` stop reason).
- **JSON schema for `report.json`** — Pydantic `Report` model in `reporting/_models.py` defines the full shape of the product evaluation report; `schemas/report.schema.json` is auto-generated via `make generate-schema` and CI-guarded by `make check-schema`. `save_report()` validates output through the model before writing. Intermediate TypedDicts (`TurnReport`, `SessionReport`, etc.) promoted to Pydantic BaseModels.

### Changed

- **Decoupled `experiment.py` from Playwright** — `_worker` and `run_experiment` now operate on the `RunnerFactory` protocol; zero Playwright imports remain in the orchestration layer.
- **CLI fully decoupled from Playwright** — factory instantiation is now a uniform no-arg `factory_cls()` call for all runners; `HEADED` env var moved into `OrcaPlaywrightRunnerConfig.load()` alongside `ORCA_*` vars; removed the Playwright-specific "Mode: headed/headless" console output.
- **BREAKING: `runner_factory_ref` required** — `runner_factory_ref` (renamed from `runner_ref`) is now a required field in `experiment.yaml` (FQN of a `RunnerFactory` class). `schema_version` stays at `1` per the v0.x policy (no version bumps before 1.0).
- **Renamed Playwright runner** — `PlaywrightRunner` → `OrcaPlaywrightRunner`, `PlaywrightRunnerFactory` → `OrcaPlaywrightRunnerFactory`, `PlaywrightRunnerConfig` → `OrcaPlaywrightRunnerConfig`; moved from `runners/playwright/` to `runners/orca_playwright/`.
- **Playwright is now an optional dependency** — install with `pip install metis-engine[playwright]`. The Orca API runner (`metis-engine` base) needs only `httpx`.
- `Observation.discarded_message` — transports that cannot deliver the persona's prose message (e.g. when answering a form) set this field; the orchestrator records it in `TurnDiagnostics`.
- `RunConfig.fixtures` — scenario fixture names are now passed to the runner via `RunConfig`.
- `ActionSlot.required` — optional boolean for form fields.
- `ChosenAction.value` — widened from `str | None` to `str | list[str] | int | float | None` for typed form answers.

### Removed

- **REST runner stub** (`simulation/runners/rest/`) — replaced by the Orca API runner and user guide examples for writing custom runners.
- CLI no longer falls back to `PlaywrightRunnerFactory` when `runner_factory_ref` is absent.

### Fixed

---

## [0.11.1] — 2026-08-27

### Changed

- **Typing modernization** — replaced `typing_extensions.TypedDict` with `typing.TypedDict`; adopted `Self` for classmethod/validator returns in `simulation/types.py` and `evaluation/types.py`; narrowed `Any` to concrete types in `cli.py` (removed `Any` import entirely); fixed bare `dict` → `dict[str, int]` in `RoutingSummary` and `EvalResult.merge`.
- Moved annotation-only imports into `TYPE_CHECKING` blocks (ruff TCH compliance).

### Added

- `py.typed` marker file (PEP 561).

---

## [0.11.0] — 2026-08-26

### Added

- **Product evaluation report** — the report joins each metric result onto the product profile
in `inputs/profile.yaml`, so pass rates roll up per criterion, behaviour, and task, and split
by persona and scenario. 

### Changed

- The report now holds the profile-joined data shape. The previous metric-only HTML report and
its raw per-turn `report.json` (cost and token dump) are removed; no code consumed the old
JSON shape.
- **Standardised LLM credentials on `OPENAI_API_KEY` / `OPENAI_BASE_URL`** — the
simulation user agent now reads the shared `OPENAI_API_KEY` and `OPENAI_BASE_URL` instead of
`USER_AGENT_API_KEY` and `USER_AGENT_BASE_URL`. The user-agent model stays selectable via
`USER_AGENT_MODEL`. ([#153](https://github.com/govtech-responsibleai/metis/issues/153))
- Default user-agent model is now `gpt-5.6-luna` (was `gpt-4o-mini`);
override with `USER_AGENT_MODEL`.
- **Typed session metadata construction** — `_session_to_conversational_test_case` now builds a
`ConversationalTestCaseMetadata`-typed dict at construction time (was untyped `dict` with post-hoc
field injection); `_trace_to_test_case` uses `LlmTestCaseMetadata` (replacing the deprecated
`TraceMetadata` alias). Required-nullable fields (`stop_reason`, `cancellation_available`,
`slide_image_refs`) are passed as keyword parameters and set at construction. No runtime behavior
change — purely static typing for Pyright validation.
- **Extractor re-exports pruned** — removed `OrcaChatMetadata` and `TraceMetadata` from
`metis.engine.extractor.__init__`; these types are owned by metis-library and should be imported
from `metis.library.metrics` directly.

## [0.10.0] — 2026-08-20

### Added

- **Observable execution metadata for metrics** — the Langfuse extractor now writes three fields into per-trace and session metadata for use by library metrics: `stop_reason` (why the session stopped), `cancellation_available` (whether the user could cancel the run), and `slide_image_refs` (paths of image/slide artifacts, in turn order, for multimodal metrics). `fetch_by_session_id` accepts new `stop_reason` and `cancellation_available` parameters; the CLI passes `record.outcome.stop_reason` and `cancellation_available=True`. Fields are marked unavailable (never invented) when a trace source does not supply them. Covered by `tests/unit/engine/test_extractor_metadata.py`. ([#150](https://github.com/govtech-responsibleai/metis/issues/150))
- **Resumable simulation** — `metis engine simulate --resume --experiment-dir <output dir>` and `metis engine run --resume --experiment-dir <output dir>` continue one named simulation output. Resume reads the experiment and fixtures from that directory's frozen `inputs/` snapshot, retries only missing, invalid, or `system_error` records, and appends to the simulation log. `simulate` and `run` print the exact resume command next to the evaluate command, so continuing an interrupted run never depends on a timestamp. `--resume` with `--input-dir` exits 1 and lists the outputs that exist for the experiment `id`.

### Changed

- **BREAKING: Split simulation and evaluation commands** — `metis engine simulate --input-dir <dir>` now writes simulation records only, and prints the exact `evaluate` command for the output directory it created. Use `metis engine evaluate --experiment-dir <output dir>` to score one simulation output, or `metis engine run --input-dir <dir>` for the combined flow. `evaluate` names its target directly, so the scored result never depends on timestamps; it exits 1 with a clear message when the path is absent or holds no `inputs/` snapshot. Simulation keeps its live TUI, while evaluation uses a normal progress bar and writes one complete `logs/evaluate.log`. `--langfuse-timeout` moved from `simulate` to `evaluate` and `run`; `--no-tui` controls simulation only.
- **Simulation summary reports outcome categories** — the final summary line now breaks runs down by `stop_reason` (`N goal achieved, N abandoned, N timeout, N error`) instead of a binary `passed`/`failed` split, so abandoned and timed-out runs are no longer conflated with errors. ([#160](https://github.com/govtech-responsibleai/metis/issues/160))

### Fixed

- **TUI panels jump and flicker during simulation** — stray writes to stderr (structlog `print("")` newlines, stdlib handler leaks, direct `console.print()` calls) corrupted the alternate screen buffer; now fully isolated via `DropEvent`, muted stdlib handler, and TUI-guarded console output
- **TUI tail content shifts unpredictably** — long log entries wrapped to variable row counts causing multi-row jumps; entries are now truncated to 1 visual row and rendered top-anchored with bottom padding
- **Ctrl+C requires pressing twice to stop** — first Ctrl+C now sets a `shutdown_event` checked by workers between runs for graceful stop; second Ctrl+C force-exits

## [0.9.0] — 2026-08-20

### Added

- `**EvalDurations` dataclass** — typed replacement for the untyped `dict[str, float]` timings field; carries `turn_metrics_seconds` and `session_metrics_seconds` for clear phase-level profiling
- `**EvalResult.session_results**` — structured `list[SessionResult]` field symmetric with `turn_results`; session→report conversion now happens in the reporting layer, not the orchestrator
- **Report-ready types** (`reporting/_types.py`) — `TurnReport`, `SessionReport`, `TurnMetricResult`, `SessionMetricResult`, `PersonaContext`, `TaskContext` moved from extractor and generator into a dedicated module; eliminates `TYPE_CHECKING` circular-import workaround in `_html_sections.py`

### Changed

- **BREAKING: Evaluation result type renames** — `TurnResult.test_case` → `.llm_test_case`, `SessionResult.test_case` → `.conversational_test_case`, `.metrics` → `.metric_results` on both; `EvalResult.test_results` → `.turn_results`, `.timings` → `.durations` (now `EvalDurations`)
- **BREAKING: Removed `EvalResult.test_cases` and `EvalResult.trace_routing`** — `test_cases` was redundant (same objects live in each `TurnResult.llm_test_case`); `trace_routing` was unused scaffolding (always `{}`). Routing info is now derived from test case metadata in the report converter.
- **BREAKING: JSON report schema** — output keys renamed: `"test_cases"` → `"turn_results"`, `"session_metrics"` → `"session_results"`, `"timings"` / `"phase_timings"` → `"durations"` (object with `turn_metrics_seconds`, `session_metrics_seconds`); `"routed_to"` field now derived from trace metadata
- **Reporting module naming** — `test_results` parameter/variables → `turn_results`, `session_metrics` → `session_results` across `generator.py`, `_aggregation.py`, `_html_sections.py`; `TurnMetricsEntry` → `TurnReport`, `SessionMetricsEntry` → `SessionReport`
- **Session conversion moved to report generator** — orchestrator now returns only structured results; `_convert_session_results()` in `generator.py` handles the projection (symmetric with `_convert_turn_results()`)
- `**SessionReport` trimmed** — removed `num_turns` and `turns` fields (conversation content was never rendered; available via `SessionResult.conversational_test_case` if needed)
- **Extractor `__init__` exports pruned** — removed re-exports of report-format types (`SessionMetricResult`, `SessionMetricsEntry`, `SessionToolCallData`, `SessionTurnData`) that now live in `reporting._types`
- **Restored example experiment scenarios** — uncommented all scenarios and metric refs in `example-experiment/experiment.yaml` that were temporarily disabled during the v0.8.0 library rollback (97cee19)

## [0.8.0] — 2026-08-19

### Added

- **Simulation user-agent LLM is now configurable via environment variables** — the user agent built its OpenAI client with no arguments (`AsyncOpenAI()`), so the API key came only from the implicit `OPENAI_API_KEY` and the endpoint could not be overridden. Added `USER_AGENT_API_KEY` (falls back to `OPENAI_API_KEY`) and `USER_AGENT_BASE_URL` (unset → default OpenAI endpoint), mirroring the judge model's `JUDGE_*` variables. Lets the simulation LLM target any OpenAI-wire-compatible provider (e.g. Platform AI) without code changes. ([#151](https://github.com/govtech-responsibleai/metis/issues/151))

### Changed

- **Deprecated `task`/`task_id` metadata replaced with `scenario`/`scenario_id`** — the Langfuse extractor now writes `scenario` and `scenario_id` into trace metadata (previously `task` and `task_id`); the reporting pipeline reads `scenario_id` throughout. The `fetch_by_session_id` parameter was renamed from `task` to `scenario`. Delegation extraction's `"task"` field (sub-agent instruction) is unrelated and unchanged.
- **Reporting module refactored for readability** — split 1033-line `generator.py` into 4 focused modules: `_aggregation.py` (single source of truth for metric pass/fail/skip counts), `_styles.py` (CSS constant), `_html_sections.py` (5 composable section renderers), and a slimmed-down `generator.py` (orchestration only). Removed dead code (`render_failure_cards` — computed but never rendered in original), relocated misplaced logic (`_extract_failures` → `_html_sections.py`), and pruned 7 orphaned CSS classes. Public API unchanged. ([#107](https://github.com/govtech-responsibleai/metis/issues/107))
- **Extractor type annotations** — added explicit type annotations to all Langfuse observation extraction helpers (`_extract_tool_calls`, `_extract_delegation`, `_extract_spoke_context`, `_extract_assistant_messages`, `_extract_subagent_output`, `_extract_clarification_requests`, `_extract_orca_chat_metadata`), the `_TraceExtraction` dataclass, `FetchLangfuseResult`, and local variables in `fetch_by_session_id`; replaced bare `list`/`dict`/`Any` with concrete SDK types (`ObservationsView`, `TraceWithDetails`, `LLMTestCase`, `ConversationalTestCase`) and shared TypedDicts from `metis-library` (`PriorTurn`, `Delegation`, `ChatMessage`, `ObservationSummary`, `ToolCallSummary`); construction sites now use typed constructors (`PriorTurn(...)`, `Delegation(...)`, `ObservationSummary(...)`, `ToolCallSummary(...)`)

### Fixed

- **Response extraction returns user's own message** — narrowed selector from `.message-user, .message-assistant` to `.message-assistant` only; previously, if the user's message was the last match, the LLM user-agent saw its own input echoed as the "assistant response"
- **Nav buttons leak into LLM action space** — expanded the button denylist from 4 inline checks to 13 entries in a named array (`buttonDenylist`); buttons like "reasoning", "dismiss error", "/agents" no longer appear as interactive elements
- **HTML report missing task descriptions and persona context** — CLI now builds `task_contexts` from experiment scenarios and run records and passes it to `generate_report()`; each task section renders scenario description, fixtures, and all personas with per-persona outcome (stop reason, turns, duration). Added `PersonaContext` type and multi-persona rendering support.
- **Python 3.14 evaluation compatibility** — disable DeepEval's async execution via `AsyncConfig(run_async=False)` to work around event-loop re-entrancy failure (likely `nest_asyncio` incompatibility with Python 3.14's stricter task state). Previously crashed all sessions with 2+ metrics per test case.
- **TUI dashboard missing worker attribution** — active runs now display their worker ID (`[w0]`, `[w1]`, …) so concurrent scenarios are immediately identifiable
- **Log tail missing run context** — tail lines now include a `[scenario:persona]` prefix when those keys are present, making interleaved errors attributable without cross-referencing per-run files
- **structlog contextvars not bound per-run** — concurrent workers now bind `scenario_id`, `persona_id`, and `trial` to structlog context before each run (previously only `worker` was bound)

## [0.7.0] — 2026-08-07

### Added

- **User guide** — `docs/guide/engine.md` covering prerequisites, quick start, experiment configuration, CLI reference, writing custom metrics, and troubleshooting
- **Runner ABC** (`simulation/runner.py`) — transport-agnostic interface (`setup`, `send_turn`, `teardown`, `get_session_id`, `recover`)
- **Orchestrator** (`simulation/orchestrator.py`) — turn-loop logic extracted from `_environment.py`
- **PlaywrightRunner** (`simulation/runners/playwright/`) — first Runner implementation
- **REST runner stub** (`simulation/runners/rest/`)
- **Action protocol** — `ActionSlot` + `ChosenAction`; LLM picks from a closed vocabulary instead of inventing selectors
- `**Observation` model** — replaces `UIState` at the interface boundary
- **Per-run context isolation** — fresh `BrowserContext` per run; `setup()` logs in, `teardown()` closes
- **Three-layer simulation resilience** — automatic retry/recovery so runs rarely end in `system_error`:
  - *Action layer* — intent-based element resolver with fallback strategies; tenacity-backed retry with exponential backoff and point-of-no-return tracking (no duplicate submissions)
  - *Turn layer* — typed failure classification, lightweight page recovery (`_recover_page`), check-before-resend pattern for post-submission failures, consecutive-failure escalation to run layer
  - *Run layer* — configurable retry budget (default: 2 retries) with full browser context teardown/rebuild and re-authentication
- **Typed exception hierarchy** (`simulation/exceptions.py`) — `SimulationError` base with `TurnRecoverableError`, `RunRecoverableError`, and `ResponseTimeoutError` branches; drives structured error routing between layers
- **Resilience diagnostics** — `TurnDiagnostics`, `ActionRetry`, and `RunFailure` models on `ConversationTurn` and `RunRecord` for post-hoc failure analysis; `RunRecord` schema bumped to v2
- `**RetryConfig**` — nested config block in `HarnessConfig` with tunable budgets for action attempts, turn retries, consecutive-failure limits, and run retries
- **Per-scenario retry override** — `max_run_retries` field on `Scenario` (optional; `null` uses global default)
- **Per-scenario simulation limits** — `Scenario` now accepts `max_turns` (default: 20) and `timeout_minutes` (default: 15) to cap how many conversation turns and how long each scenario's simulation run is allowed to take; `response_wait_ms` (already on `Scenario`) is now the authoritative runtime timeout for waiting on the target's response (previously only recorded in output; runtime used `HarnessConfig.timeouts.response_wait_ms`)
- **Concurrent simulation** — `--concurrency N` flag runs N browser contexts in parallel on a single browser process; round-robin run distribution across workers
- **Async Playwright harness** — full async conversion (`playwright.async_api`) of auth, page actions, UI capture, and environment modules
- **Async OpenAI client** — `AsyncOpenAI` for non-blocking LLM calls across concurrent workers
- **Worker isolation** — each worker gets its own BrowserContext, page, login session, and `structlog.contextvars` binding (`worker=w0`, `worker=w1`, …)
- **Crash resilience** — individual `run_simulation()` failures are caught per-run (worker continues remaining runs); `generate_opening()` failures produce a `system_error` record instead of crashing
- **Per-worker log tail panels** — TUI splits the log tail into N vertically-stacked panels (one per worker) so each shows a clean sequential narrative; events without a worker key broadcast to all panels

### Changed

- `**UserAgentInput**` — removed `ui_state` and `action_feedback`; now `observation` + `run_meta` only
- `**UserAgentOutput**` — `ui_actions: list[UIAction]` → `actions: list[ChosenAction]`
- `**harness/` dissolved** — `__init__.py` → `experiment.py`; `_environment.py` split into `orchestrator.py` + `runners/playwright/`
- **Prompts** — generic action vocabulary (id/kind/label/options) replaces CSS-specific instructions
- `run_experiment()` accepts `concurrency: int` parameter (default 1 preserves sequential behaviour)
- CLI `simulate` command accepts `--concurrency / -c` option (min 1)
- `log_format` CLI option typed as `Literal["text", "json"]` for pyright correctness
- **Orca DOM selectors** — replaced all fragile `[class*="..."]` attribute-contains selectors with Orca's actual DOM structure: `.message-user`/`.message-assistant` for messages, "Stop generating" button + empty `.message-assistant` for processing detection, "Send message" text for button filtering, "Dismiss error" button for error detection, "Open files panel" for artifacts panel, structural SVG/canvas selectors for charts. Removed dead chip/suggestion selectors (don't exist in Orca)

### Fixed

- **"Response cancelled" after upload/submit** — file uploads and submit-type button clicks now wait for Orca processing to settle (spinner/typing/"Stop generating" poll) before proceeding to `send_message`; additionally, `send_message` detects "Response cancelled" in captured UI state and waits for the real response
- **Failed uploads bypass dedup** — file only added to `uploaded_files` set after UI visibility verification, so failed uploads can be retried
- **Chart screenshots overwrite across turns** — `capture_inline_charts` takes a `turn` parameter; filenames are now `turn-{T}-chart-{N}.png`
- **Downloaded artifacts collide across turns** — downloads go to `run_dir/artifacts/turn-{N}/` subdirectories instead of a flat `artifacts/` folder
- **Off-by-one kills last turn** — removed redundant `>= max_turns` check at bottom of loop; single `> max_turns` guard at top ensures all turns execute fully
- `**fill()` + `press("Enter")` race condition** — added 200ms delay between fill and Enter to avoid keystroke being dropped when Orca's JS reacts to input events
- **Temp directory leak on upload retry** — replaced bare `tempfile.mkdtemp()` with `TemporaryDirectory()` context manager
- **Download counter misleading** — separate counter for download-type artifacts only
- **Stale-state detection false positive** — "page unchanged after form submit" warning fired incorrectly because the pre-submit text snapshot was captured after `_wait_for_processing` already consumed the processing time; moved snapshot to before action execution
- **Disabled form elements reported to LLM** — `capture_ui_state` now excludes disabled inputs/selects/buttons (`:not([disabled])`), preventing the LLM from attempting to fill elements Orca has locked after form submission
- **Button clicks always wait for processing** — removed brittle submit-keyword regex; all `ButtonClickAction` clicks now trigger `_wait_for_processing` and the form processing branch, eliminating timeouts from unrecognized button labels like "Continue"

## [0.6.0] — 2026-08-06

### Added

- **TUI control plane** — Rich-based live dashboard with progress bars (scenarios + runs), per-run status with turn detail, and a log tail panel; auto-activates in TTY, disabled in CI/pipes or with `--no-tui`
- **Structured per-run log files** — each simulation run writes a DEBUG-level log to `logs/simulate-<scenario>_<persona>-<trial>.log`; format controlled by `--log-format` (text or json)
- **Orchestration index** — `logs/simulate.log` records scenario/run start and completion events with pointers to per-run detail logs
- **CLI flags** — `--no-tui`, `--quiet`, `--log-format {text,json}`, `--log-dir <path>`
- **Final summary** — static summary printed after pipeline completes (run counts, pass/fail, log location)
- **Graceful shutdown** — first Ctrl+C finishes current turn; second aborts immediately
- **Report task context** — HTML report now renders per-scenario context (description, persona, fixtures, outcome/duration) in an info card above each task section; `TaskContext` TypedDict exported from `metis.engine.reporting`

### Changed

- `run_experiment()` and `run_simulation()` accept optional TUI/logging hooks (`state`, `orchestration_logger`, `log_router`, `tui_ctx`); existing behaviour preserved when called without them
- Harness binds `structlog.contextvars` (scenario_id, persona_id, trial) per run for structured log routing
- `configure_logging()` called before harness import with `cache_logger_on_first_use=False` to support dynamic processor chain updates
- `generate_report()` and `save_html_report()` accept optional `task_contexts` parameter for enriching the HTML report with scenario metadata
- Failure-reason snippets in HTML report expanded from 120 to 300 characters

## [0.5.0] — 2026-08-05

### Changed

- **BREAKING: `ExperimentTask` renamed to `Scenario`** — the experiment schema field `tasks` is now `scenarios`; `RunConfig.task` is now `RunConfig.scenario`; all CLI error messages, prompts, and log lines updated to use "scenario" terminology
- Updated metric FQNs in `experiment.yaml`, README, and orchestrator docstring to use package-level paths (`metis.library.metrics.X` instead of `metis.library.metrics.<module>.X`)

## [0.4.0] — 2026-08-04

### Changed

- **BREAKING: Simulation type renames** — `SessionConfig` / `SessionRecord` / `SessionOutcome` / `SessionMeta` renamed to `RunConfig` / `RunRecord` / `RunOutcome` / `RunMeta` to avoid confusion with Langfuse sessions; output folder renamed from `sessions/` to `runs/`, manifest from `session-manifest.json` to `run-manifest.json`
- **BREAKING: User-agent type renames** — `TurnPayload` → `UserAgentInput`, `UserAgentResponse` → `UserAgentOutput`; field renames: `UserAgentOutput.action` → `.decision`, `ConversationTurn.system_response` → `.target_response`, `UIState.agent_labels` → `.target_status_labels`
- **Simulation API** — `fixtures_dir` is now a required parameter on `run_experiment` / `run_simulation` (removed dead `_DEFAULT_FIXTURES_DIR` fallback); `RunConfig` construction inlined inside `run_simulation`
- **Extractor refactor** — introduced `_TraceExtraction` dataclass to bundle per-trace extraction results; `_trace_to_test_case` and `_session_to_conversational_test_case` now accept pre-extracted data instead of raw traces, eliminating redundant extraction passes and the `langfuse` client parameter on `_session_to_conversational_test_case`
- **Removed `_types.py` indirection** — deleted `simulation/harness/_types.py` re-export shim; all imports come directly from `simulation/types.py`
- **Test layout** — relocated unit tests from co-located `*_test.py` files in the source tree (`cli_test.py`, `simulation/schema_test.py`) to `tests/unit/engine/` per the monorepo architecture spec (§7)
- **Test naming** — renamed to `test_*.py` convention consistent with the rest of the monorepo
- **pytest config** — removed `packages/*/src/metis/*/` and `apps/*/src/metis/*/` workarounds from root `testpaths`; tests are now discoverable via `make test-unit` as intended

### Fixed

- **CLI test assertions** — corrected 9 tests that asserted error messages on stderr when `_validate_inputs` writes to stdout via `metis.core.console`; these tests were silently never running under `make test-unit`

## [0.3.0] — 2026-08-03

### Removed

- **BREAKING:** Metrics module removed from engine. All 53 metric classes now live in `metis.library.metrics`. Import paths change from `metis.engine.metrics.<module>.<Class>` to `metis.library.metrics.<module>.<Class>`.

### Changed

- **Structured logging** — replaced all raw `print()` and `logging` calls with `metis.core.console` (Rich-formatted stdout) and `metis.core.logging.get_logger` (structured diagnostics to stderr) across CLI, simulation harness, user agent, and report generator
- `extractor/types.py` — `TraceMetadata`, `OrcaChatMetadata`, and `ClarificationRequest` are now re-exported from `metis.library.metrics._types` (backwards-compatible for engine consumers importing from `metis.engine.extractor`).
- FQN references in `experiment.yaml` and `simulation/types.py` updated to `metis.library.metrics.*`.

## [0.2.1] — 2026-07-31

- **Simulation file-existence check** — harness now verifies files exist before attempting upload, preventing runtime errors from missing fixtures
- **DeepEval class name resolution** — corrected metric class lookup in `metrics.universal` so dynamically referenced DeepEval metrics resolve correctly
- **User-agent upload guard** — added prompt instruction reminding the LLM user-agent not to reference non-existent files

## [0.2.0] — 2026-07-30

Full-fidelity migration of `orca-agentic-evals` v0.2.0 into the metis monorepo. All source modules land under `metis.engine` with namespace rewrites but no logic changes.

### Added

- **Simulation harness** — Playwright-based browser automation that drives a target system's UI end-to-end, with LLM-powered user personas generating realistic multi-turn conversations
- **Experiment schema** — declarative `experiment.yaml` format defining personas, tasks, fixtures, metric references, and trial counts; validated by Pydantic v2 with upfront fail-fast checks
- **Langfuse trace extractor** — fetches execution traces by session ID and builds DeepEval test cases (both per-turn `LLMTestCase` and session-level `ConversationalTestCase`)
- **Evaluation orchestrator** — dynamically instantiates metrics from FQN references, routes test cases to the appropriate metric type, and collects scored results
- **50+ evaluation metrics** across five modules:
  - `metrics.orchestration` (16) — routing accuracy, clarification judgement, decomposition quality, delegation correctness, synthesis faithfulness, cross-agent context retention, and more
  - `metrics.analysis` (16) — analytical correctness, scope, data ingestion accuracy, chart fitness/necessity/granularity, report coherence/completeness/format, outlier handling, insight quality
  - `metrics.presentation` (3) — slide spec compliance, cross-slide logical flow, deck source faithfulness
  - `metrics.universal` (12) — constraint adherence, turn budget, clarification precision, step efficiency, bounded troubleshooting, assumption transparency, failure report quality
  - `metrics.session` (9) — session-level variants for completeness, faithfulness, context retention, decomposition accuracy, troubleshooting, and efficiency
- **Report generator** — produces terminal summary, machine-readable JSON, and self-contained HTML report
- **CLI commands** — `metis engine simulate --input-dir <path>` with options for Langfuse timeout, verbosity, and headed browser mode (`HEADED=true`)
- **Input validation** — 8-step upfront validation (directory exists, schema parses, no duplicate IDs, persona refs resolve, fixtures exist, metric FQNs importable) with actionable error messages and exit code 1
- **Example experiment** — working reference with personas, tasks, CSV fixtures, and metric configurations
- **JSON Schema export** — `experiment.schema.json` generated from Pydantic models, with CI sync check
- **Package-local Makefile** — `generate-schema`, `check-schema`, `install-playwright` targets

### Changed

- Version bumped from `0.1.0` to `0.2.0`
- Package description updated to reflect expanded scope
- Public API now exports `evaluate`, `fetch_by_session_id`, `generate_report`, and `get_langfuse_client`
- CLI ported from argparse to Typer, composable into the unified `metis` CLI as `metis engine`
- Python 3.11 modernization: removed `eval-type-backport`, applied `UP` ruff rules (union syntax, modern type hints)

### Removed

- Placeholder `DemoMetric` and direct `metis-core` re-exports from the public API

## [0.1.0] — 2026-07-23

Initial release. Corresponds to `orca-agentic-evals` v0.1.0 — evaluation framework hardcoded for ORCA (MOM).

### Added

- **Simulation harness** — Playwright-based browser automation driving multi-turn conversations against a target UI
- **LLM-powered user agent** — OpenAI-backed persona that generates realistic user messages during simulation
- **Langfuse trace adapter** — `fetch_traces`, `session_to_conversational_test_case` for building DeepEval test cases from Langfuse session traces; typed with `SessionContext`, `ClarificationRequest`, `OrcaChatMetadata`, `TraceMetadata`
- **Evaluation metrics** — initial metric set using DeepEval, covering orchestration, analysis, and universal dimensions
- **CLI** — argparse-based `simulate` and `evaluate` subcommands
- **Makefile** — `lint`, `format`, `typecheck` targets via Ruff
- **Documentation** — architecture diagram, evaluation framework reference, `.env.example`

### Changed

- Adopted `uv` + `direnv` for dependency and environment management (replaced raw pip)
- Langfuse client refactored: top-level import, required keyword-only arg, typed return values
- Removed legacy TypeScript runner (`runner.ts`, `chat.ts`, `test-cases/`)
- Removed dead code: `check_routing_passed`, `--dedup` flag, `deduplicate_traces`, `build_test_cases_from_langfuse`, `artifact_registry` references

