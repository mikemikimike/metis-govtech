# Changelog

All notable changes to `metis-engine` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

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

## [0.1.0] — 2026-06-15

Initial release — scaffold with CLI skeleton and basic trace-file ingestion.
