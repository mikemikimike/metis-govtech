# schemas/

The generated JSON Schema describes authoring drafts of the shared Specification in
`metis.core.specification`. The wizard adds YAML persistence methods. Editors can use this
schema for draft completion. The domain Specification contains a Profile and an Experiment;
the generated schema describes their flat document. Use the engine specification schema for executable files.

The JSON files here are **auto-generated**. Do not edit them directly; they will be overwritten.

## Source of truth

| Schema file | Pydantic model | Version constant | Source file |
|---|---|---|---|
| `specification.schema.json` | `Specification` | `_SPECIFICATION_VERSION` | `packages/core/src/metis/core/specification.py` |

`Specification.to_yaml()` preserves the draft fields and writes the schema version, ID, and runner reference before the Profile fields. `schema_version` is defaulted rather than required, because the specification is machine-written: a specification without the key still loads and is stamped on the next save.

## How to modify the schema

1. Edit the shared Pydantic models in `packages/core/src/metis/core/profile.py`, `packages/core/src/metis/core/experiment.py`, and `packages/core/src/metis/core/specification.py`
2. Determine whether the change is breaking (see [Version bump rules](#version-bump-rules) below); if so, increment `_SPECIFICATION_VERSION` and update the `Literal[N]` annotation on `Specification.schema_version` to match
3. Run `make generate-schema` to regenerate the schema file
4. Update `packages/engine/example-experiment/specification.yaml` if the model changed
5. Commit the updated schema file alongside the model change; note any version bump in the commit message

## Automated checks

`make check-schema` runs in CI (`make ci`) and fails if the committed schema does not match what Pydantic generates now (a stale file — a forgotten `make generate-schema`). The wizard schema test (`tests/unit/wizard/domain/test_specification.py`) also fails if the example specification does not validate against the committed schema or does not parse with the model.

These catch forgotten regeneration runs and broken examples, but **not** forgotten version bumps — if you make a breaking change and don't increment `_SPECIFICATION_VERSION`, the checks won't notice.

## Version bump rules

A change requires a version bump if data valid under version N would **fail `model_validate()` under the new model** — data compatibility only, i.e. whether old specifications can still be loaded.

| Change type | Example | Bump? | Why |
|---|---|---|---|
| New optional field | `tags: list[str] = []` | No | Old data lacks it; Pydantic fills the default |
| New required field | `owner: str` | **Yes** | Old data lacks it; validation fails |
| Remove field | Drop `detail` | No | Unknown fields are ignored in old data |
| Change field type | `num_trials: int` → `float` | **Yes** | Old data has the wrong type |
| Rename field | `description` → `summary` | **Yes** | Old data has the old name |

Versions are integers (1, 2, 3, ...), not semver: "if this doesn't match what you expect, you cannot parse this." The version is independent of the package version.
