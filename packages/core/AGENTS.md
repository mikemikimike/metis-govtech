# metis-core

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Core data models and abstractions for the METIS suite. Zero workspace dependencies — only Pydantic v2 + stdlib.

## Package-Specific Notes

- Dependencies: Pydantic v2, structlog, Rich (plus stdlib). Zero workspace dependencies.
- Public logging API: `from metis.core.logging import get_logger, configure_logging`
- Public console API: `from metis.core.console import console`

- `metis.core.profile` owns Target context, Features, Behaviours, and Criteria.
- `metis.core.experiment` owns Personas, Scenarios, Tasks, and execution settings.
- `metis.core.specification` combines a Profile and an Experiment. Its document
  adapter keeps YAML and API JSON flat.
  Keep draft construction separate from complete execution validation.
- `traces.py`: `Observation`, `Trace` and `GradingInput`, the read-only input of every grader
  run. Frozen, tuple collections. `Trace.root` is METIS's port of Langfuse's
  `isRootObservation = true` filter.
- `grading.py`: `GraderResult`/`GradingOutput` (what a grader returns: a score, never a
  pass/fail) and `RecordedResult` (the outcome after the orchestrator applies the threshold).
- `reporting.py`: `EvaluationResults` (`outputs/reports/results.json`), one `GraderRecord`
  per grader per session. It is version-guarded like `TrialRecord` and has no published
  schema file.
