# Changelog

All notable changes to `metis-engine` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Reporting module refactored for readability** — split 1033-line `generator.py` into 4 focused modules: `_aggregation.py` (single source of truth for metric pass/fail/skip counts), `_styles.py` (CSS constant), `_html_sections.py` (5 composable section renderers), and a slimmed-down `generator.py` (orchestration only). Removed dead code (`render_failure_cards` — computed but never rendered in original), relocated misplaced logic (`_extract_failures` → `_html_sections.py`), and pruned 7 orphaned CSS classes. Public API unchanged. ([#107](https://github.com/govtech-responsibleai/metis/issues/107))

### Fixed

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
- **`Observation` model** — replaces `UIState` at the interface boundary
- **Per-run context isolation** — fresh `BrowserContext` per run; `setup()` logs in, `teardown()` closes

- **Three-layer simulation resilience** — automatic retry/recovery so runs rarely end in `system_error`:
  - *Action layer* — intent-based element resolver with fallback strategies; tenacity-backed retry with exponential backoff and point-of-no-return tracking (no duplicate submissions)
  - *Turn layer* — typed failure classification, lightweight page recovery (`_recover_page`), check-before-resend pattern for post-submission failures, consecutive-failure escalation to run layer
  - *Run layer* — configurable retry budget (default: 2 retries) with full browser context teardown/rebuild and re-authentication
- **Typed exception hierarchy** (`simulation/exceptions.py`) — `SimulationError` base with `TurnRecoverableError`, `RunRecoverableError`, and `ResponseTimeoutError` branches; drives structured error routing between layers
- **Resilience diagnostics** — `TurnDiagnostics`, `ActionRetry`, and `RunFailure` models on `ConversationTurn` and `RunRecord` for post-hoc failure analysis; `RunRecord` schema bumped to v2
- **`RetryConfig`** — nested config block in `HarnessConfig` with tunable budgets for action attempts, turn retries, consecutive-failure limits, and run retries
- **Per-scenario retry override** — `max_run_retries` field on `Scenario` (optional; `null` uses global default)
- **Per-scenario simulation limits** — `Scenario` now accepts `max_turns` (default: 20) and `timeout_minutes` (default: 15) to cap how many conversation turns and how long each scenario's simulation run is allowed to take; `response_wait_ms` (already on `Scenario`) is now the authoritative runtime timeout for waiting on the target's response (previously only recorded in output; runtime used `HarnessConfig.timeouts.response_wait_ms`)
- **Concurrent simulation** — `--concurrency N` flag runs N browser contexts in parallel on a single browser process; round-robin run distribution across workers
- **Async Playwright harness** — full async conversion (`playwright.async_api`) of auth, page actions, UI capture, and environment modules
- **Async OpenAI client** — `AsyncOpenAI` for non-blocking LLM calls across concurrent workers
- **Worker isolation** — each worker gets its own BrowserContext, page, login session, and `structlog.contextvars` binding (`worker=w0`, `worker=w1`, …)
- **Crash resilience** — individual `run_simulation()` failures are caught per-run (worker continues remaining runs); `generate_opening()` failures produce a `system_error` record instead of crashing
- **Per-worker log tail panels** — TUI splits the log tail into N vertically-stacked panels (one per worker) so each shows a clean sequential narrative; events without a worker key broadcast to all panels

### Changed

- **`UserAgentInput`** — removed `ui_state` and `action_feedback`; now `observation` + `run_meta` only
- **`UserAgentOutput`** — `ui_actions: list[UIAction]` → `actions: list[ChosenAction]`
- **`harness/` dissolved** — `__init__.py` → `experiment.py`; `_environment.py` split into `orchestrator.py` + `runners/playwright/`
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
- **`fill()` + `press("Enter")` race condition** — added 200ms delay between fill and Enter to avoid keystroke being dropped when Orca's JS reacts to input events
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
