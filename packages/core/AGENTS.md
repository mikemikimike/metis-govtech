# metis-core

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Core data models and abstractions for the METIS suite. Zero workspace dependencies — only Pydantic v2 + stdlib.

## Package-Specific Notes

- Dependencies: Pydantic v2, structlog, Rich (plus stdlib). Zero workspace dependencies.
- Public logging API: `from metis.core.logging import get_logger, configure_logging`
- Public console API: `from metis.core.console import console`

- `metis.core.profile` owns Product context, Features, Behaviours, and Criteria.
- `metis.core.experiment` owns Personas, Scenarios, Tasks, and execution settings.
- `metis.core.specification` combines a Profile and an Experiment. Its document
  adapter keeps YAML and API JSON flat.
  Keep draft construction separate from complete execution validation.
- `metis.core.reporting` owns the serializable grader-result types and
  `EvaluationResults`, the `reports/results.json` file that `metis-engine` writes and
  `metis-insights` reads. It is version-guarded like `TrialRecord` and has no published
  schema file.
