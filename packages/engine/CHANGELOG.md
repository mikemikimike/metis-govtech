# Changelog

All notable changes to `metis-engine` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.6.0] — 2026-08-05

_Unreleased_

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
