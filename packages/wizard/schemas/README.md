# schemas/

JSON Schema files generated from the Pydantic models in `src/metis/wizard/domain/profile.py`. They describe the structure of `profile.yaml` — the portable product profile the wizard writes and the engine reads — and are used by IDE tooling (schema-aware editors, YAML validators) to provide autocomplete and inline validation.

The JSON files here are **auto-generated**. Do not edit them directly; they will be overwritten.

## Source of truth

| Schema file | Pydantic model | Version constant | Source file |
|---|---|---|---|
| `profile.schema.json` | `ProductProfile` | `_PROFILE_VERSION` | `src/metis/wizard/domain/profile.py` |

`ProductProfile.to_yaml()` is a 1:1 round-trip of the model (`yaml.dump(self.model_dump(mode="json"))`), so the schema describes `profile.yaml` exactly. `schema_version` is defaulted rather than required, because the profile is machine-written: a profile without the key still loads and is stamped on the next save.

## How to modify the schema

1. Edit the Pydantic model in `src/metis/wizard/domain/profile.py`
2. Determine whether the change is breaking (see [Version bump rules](#version-bump-rules) below); if so, increment `_PROFILE_VERSION` and update the `Literal[N]` annotation on `ProductProfile.schema_version` to match
3. Run `make generate-schema` to regenerate the schema file
4. Update `packages/engine/example-experiment/profile.yaml` if the model changed
5. Commit the updated schema file alongside the model change; note any version bump in the commit message

## Automated checks

`make check-schema` runs in CI (`make ci`) and fails if the committed schema does not match what Pydantic generates now (a stale file — a forgotten `make generate-schema`). The wizard schema tests (`packages/wizard/tests/test_schema.py`) also fail if the example profile does not validate against the committed schema or does not parse with the model.

These catch forgotten regeneration runs and broken examples, but **not** forgotten version bumps — if you make a breaking change and don't increment `_PROFILE_VERSION`, the checks won't notice.

## Version bump rules

A change requires a version bump if data valid under version N would **fail `model_validate()` under the new model** — data compatibility only, i.e. whether old profiles can still be loaded.

| Change type | Example | Bump? | Why |
|---|---|---|---|
| New optional field | `tags: list[str] = []` | No | Old data lacks it; Pydantic fills the default |
| New required field | `owner: str` | **Yes** | Old data lacks it; validation fails |
| Remove field | Drop `detail` | No | Unknown fields are ignored in old data |
| Change field type | `num_trials: int` → `float` | **Yes** | Old data has the wrong type |
| Rename field | `description` → `summary` | **Yes** | Old data has the old name |

Versions are integers (1, 2, 3, ...), not semver: "if this doesn't match what you expect, you cannot parse this." The version is independent of the package version.
