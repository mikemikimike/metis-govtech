# metis-engine

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Evaluation runtime — simulation harness, trace extraction, and grader execution. Report generation lives in `metis-insights`.

## Runner Contract

`docs/runner-contract.md` is normative for every `Runner` implementation. When changing a runner, `Observation`, `ActionResult`, or the orchestrator's handling of either, read it first and keep it in sync — it is the document the conformance suite in issue #358 will be written against.

## Schema Sync

`metis-core` publishes the one `specification.yaml` schema, from `SpecificationDocument` in
`packages/core/src/metis/core/specification.py`. The engine has no schema files of its own. After
you change a shared model, run:

```bash
make -C packages/core generate-schema
```

Commit the updated schema file alongside the model change.

## Schema Versioning

**v0.x policy:** v0.x releases use `schema_version: 1` for every schema and may break schemas freely — consumers pin to exact package versions.

**`next` (v1 pre-release) policy:** Every schema stays at `schema_version: 1`. Breaking changes on `next` do not bump it; record them in `MIGRATION.md` instead.

**v1.x policy (planned):** Starting with the 1.0 release, proper schema versioning will be enforced. Breaking changes will bump `schema_version`, and migration paths will be documented. The bump checklist below applies from 1.0 onward.

When modifying `Specification` or `TrialRecord`, check whether the change is **breaking** — i.e., whether data valid under the current version would fail `model_validate()` under the new model.

**A bump is required for:** new required fields, type changes, field renames, breaking changes in nested models.

**No bump needed for:** new optional fields with defaults, removing fields (`extra="ignore"` silently drops them).

A breaking change to a nested model bumps the version of the root model that contains it:
- Shared Profile nodes, `Scenario`, `Task`, and `Criterion` → bump `Specification`
- `TrialConfig`, `TrialOutcome`, `TrialFailure`, `Artifact` → bump `TrialRecord`

### Bump Checklist (applies from v1.0)

1. Increment `_SPECIFICATION_VERSION` in `metis.core.specification` or `_TRIAL_RECORD_VERSION` in `metis.core.trials`
2. Update the `Literal[N]` annotation on the model field to match
3. Run `make -C packages/core generate-schema` if `Specification` changed
4. Update `examples/gen_1-orca_api-1/specification.yaml` and `packages/testbed/wizard/cases/orca/outputs/specification.yaml` if affected
5. Note the schema version change in the commit message

See `packages/core/schemas/README.md` for the version policy.

## Pyright Configuration

The workspace disables `reportIncompatibleMethodOverride`. It was added for DeepEval's
`BaseMetric.__name__`; the redesign (#428) removed that cause and no override errors remain,
so re-enabling it is a safe follow-up.

## Test Style

- Unit tests do not touch the network. Build `Trace` / `GradingInput` objects directly for
  grader and orchestrator tests.
- To test the Langfuse fetch, call `fetch_session` with a fake client whose `get_many` answers
  by filter column (see `tests/unit/engine/test_extractor_fetch.py`), so a fetch that reuses the
  session-filtered rows as a trace's observations (issue #435) fails. Do not hit the live
  Langfuse API.
