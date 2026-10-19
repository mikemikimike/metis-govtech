# metis-core

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Core data models and abstractions for the METIS suite. Zero workspace dependencies — only Pydantic v2 + stdlib.

## Shared schemas

Core owns all new shared file contracts. Published
`*.schema.json` files belong in `packages/core/schemas/` and must be generated from
core models. Register new schemas in `scripts/generate_schema.py`. Run
`make -C packages/core generate-schema` and `make -C packages/core check-schema`.
Private runtime models and API models stay in their owning packages. See the
[schema guide](schemas/README.md).

## Package-Specific Notes

- Dependencies: Pydantic v2, structlog, Rich (plus stdlib). Zero workspace dependencies.
- Public logging API: `from metis.core.logging import get_logger, configure_logging`
- Public console API: `from metis.core.console import console`

- `metis.core.profile` owns Target context, Features, Behaviours, and Criteria.
- `metis.core.experiment` owns Personas, Scenarios, Tasks, and execution settings.
- `metis.core.specification` combines a Profile and an Experiment. Its document
  adapter keeps YAML and API JSON flat.
  Keep draft construction separate from complete execution validation.
  `SpecificationDocument` is the source of `schemas/specification.schema.json`, the one
  published schema for `specification.yaml`. After changing it or a model it contains, run
  `make -C packages/core generate-schema` and commit the result.
- `traces.py`: `Observation`, `Trace` and `GradingInput`, the read-only input of every grader
  run. Frozen, tuple collections. `Trace.root` is METIS's port of Langfuse's
  `isRootObservation = true` filter.
- `grading.py`: `GraderResult`/`GradingOutput` (what a grader returns: a score, never a
  pass/fail) and `RecordedResult` (the outcome after the orchestrator applies the threshold).
- `reporting.py`: `EvaluationResults` (`outputs/reports/results.json`), one `GraderRecord`
  per grader per session. It is version-guarded like `TrialRecord` and has no published
  schema file.
- `trials.py`: `TrialRecord` (`outputs/trials/<trial>/record.json`) and the models it nests
  (`TrialConfig`, `TrialOutcome`, `TrialFailure`, `GraderRef`). The engine writes and resumes
  from it; the report reads it. Version-guarded by `_TRIAL_RECORD_VERSION`, no published
  schema file.
