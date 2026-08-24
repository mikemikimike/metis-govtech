# metis-engine

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Evaluation runtime — simulation harness, trace extraction, metric execution, and report generation.

## Schema Sync

Pydantic models in `src/metis/engine/simulation/types.py` are the source of truth for JSON Schemas in `schemas/`. After modifying any model, run:

```bash
make -C packages/engine generate-schema
```

Commit the updated schema files alongside the model change.

## Schema Versioning

When modifying `Experiment` or `SessionRecord`, check whether the change is **breaking** — i.e., whether data valid under the current version would fail `model_validate()` under the new model.

**A bump is required for:** new required fields, type changes, field renames, breaking changes in nested models.

**No bump needed for:** new optional fields with defaults, removing fields (`extra="ignore"` silently drops them).

A breaking change to a nested model bumps the version of the root model that contains it:
- `ExperimentTask`, `MetricRef`, `Persona` → bump `Experiment`
- `SessionConfig`, `SessionOutcome`, `CollectedArtifact`, `ConversationTurn` → bump `SessionRecord`

### Bump Checklist

1. Increment the relevant `_*_VERSION` constant in `simulation/types.py`
2. Update the `Literal[N]` annotation on the model field to match
3. Run `make -C packages/engine generate-schema` if the bumped model has a generated schema
4. Update `example-experiment/experiment.yaml` if affected
5. Note the schema version change in the commit message

See `schemas/README.md` for the full version bump rules table.

## Pyright Configuration

The workspace disables `reportIncompatibleMethodOverride` for this package because DeepEval's `BaseMetric.__name__` returns `Literal['Base Metric']` and every subclass override triggers false positives.

## Test Style

- Unit tests do not touch the network. Build `LLMTestCase` / `ConversationalTestCase` objects directly and assert on the metadata written by the extractor.
- To test extractor metadata injection, call `fetch_by_session_id` with a mocked Langfuse client, or test the pure helpers in isolation. Do not hit the live Langfuse API.
