# schemas/

JSON Schema files generated from the Pydantic models in `src/metis/engine/simulation/types.py`. They describe the structure of files that users author by hand — primarily `specification.yaml` — and are used by IDE tooling (schema-aware editors, YAML validators) to provide autocomplete and inline validation.

The JSON files here are **auto-generated**. Do not edit them directly; they will be overwritten.

## Source of truth

| Schema file | Pydantic model | Version constant | Source file |
|---|---|---|---|
| `specification.schema.json` | `Specification` | `_SPECIFICATION_VERSION` | `src/metis/engine/simulation/types.py` |
| `report.schema.json` | `Report` | `_REPORT_VERSION` | `src/metis/engine/reporting/_models.py` |

`TrialRecord` is code-produced (written at runtime by the simulation harness) and does not have a standalone schema file. Its version constant is `_TRIAL_RECORD_VERSION`.

## How to modify a schema

1. Edit Profile fields in `packages/core/src/metis/core/profile.py` execution inputs in `packages/core/src/metis/core/experiment.py`, or their flat document in `packages/core/src/metis/core/specification.py`, engine execution validation in `src/metis/engine/simulation/types.py`, or report fields in `src/metis/engine/reporting/_models.py`
2. Determine whether the change is breaking (see [Version bump rules](#version-bump-rules) below); if so, increment the `_*_VERSION` constant and update the `Literal[N]` annotation on the model field to match
3. Run `make generate-schema` to regenerate the schema file
4. Update `example-experiment/specification.yaml` if the `Specification` model changed
5. Commit the updated schema file alongside the model change; note any version bump in the commit message

## Automated checks

`schema_test.py` runs in CI and fails if:

- The committed schema doesn't match what Pydantic generates (stale schema file — forgotten `make generate-schema`)
- The example fixture doesn't validate against the committed schema
- The example fixture doesn't parse with the Pydantic model

This catches forgotten regeneration runs and broken examples, but **not** forgotten version bumps — if you make a breaking change and don't increment `_*_VERSION`, the test won't notice.

## Version bump rules

A change requires a version bump if data valid under version N would **fail `model_validate()` under the new model**. This covers **data compatibility** only — whether old files can be loaded. **Code compatibility** is handled by the type checker (`make check`) and tests.

| Change type | Example | Bump? | Why |
|---|---|---|---|
| New optional field | `tags: list[str] = []` | No | Old data lacks it; Pydantic fills in the default |
| New required field | `experiment_id: str` | **Yes** | Old data lacks it; validation fails |
| Remove field | Drop `target_session_id` | No | `extra="ignore"` silently drops unknown fields in old data |
| Change field type | `duration_ms: int` → `float` | **Yes** | Old data has wrong type; validation fails |
| Rename field | `turn_number` → `index` | **Yes** | Old data has old name; new field missing |
| Breaking change in nested model | New required field in `Task` | **Yes** — bump root | Old data fails nested model validation |

A breaking change to a nested model bumps the version of the root model that contains it:
- Shared Profile nodes, `Criterion`, `Persona`, `Scenario`, and `Task` → bump `Specification`
- `TrialConfig`, `TrialOutcome`, `Artifact`, `ConversationTurn` → bump `TrialRecord`

The common trap is giving a breaking field a default to avoid a bump. That's fine for genuinely optional fields, but if the field is semantically required and you're using a default as a workaround, you're hiding a real schema change. Use a bump and a migration instead.

Versions are integers (1, 2, 3, ...), not semver. A single integer means: "if this doesn't match what you expect, you cannot parse this." There is no "minor" — additive changes are invisible to consumers by design. The version is independent of the package version.

## FAQ

### Do we reject v1 data once we're on v2?

**Yes, by default.** The `_check_version` validator rejects any version that doesn't match the current constant. The failure is loud and early rather than a silent misparse deep in processing.

If you need old data to remain loadable after a bump, explicitly opt in via one of three strategies:

**1. Compatibility layer in the model validator** (preferred for transparent upgrades, few versions): detect old data in `_check_version`, transform it to the current shape, let normal validation proceed. Support only N and N-1; reject anything older.

```python
@model_validator(mode="before")
@classmethod
def _check_version(cls, data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    v = data.get("schema_version", 1)
    if v == 1:
        data["new_field"] = derive_from(data.pop("old_field", None))
        data["schema_version"] = 2
    elif v != _SPECIFICATION_VERSION:
        raise ValueError(
            f"Unsupported schema_version {v} (expected {_SPECIFICATION_VERSION})"
        )
    return data
```

**2. Standalone migration functions** (preferred for one-time bulk upgrades): write a `migrate_v1_to_v2()` that transforms old files on disk, then load normally. Keeps migration logic out of the model entirely.

**3. Discriminated union** (preferred when multiple versions must coexist at runtime without transformation):

```python
AnySpecification = Annotated[
    SpecificationV1 | SpecificationV2,
    Field(discriminator="schema_version"),
]
```

Without one of these, old files simply won't load — that's the correct default.

### Who is responsible for updating files after a bump?

For **user-authored inputs** (`specification.yaml`): the user must update their files. The validator gives a clear error message. This is a deliberate one-time migration cost — the alternative (silent default-filling of a required field) would make the version field meaningless.

For **code-produced outputs** (`record.json` session records): the harness always writes `schema_version` explicitly, so new records are always stamped correctly. Old records from a previous run will not load after a bump — use one of the coexistence strategies above if needed.

### Is version bumping enforced automatically?

Not fully — see [Automated checks](#automated-checks) above for what CI catches. Forgotten version bumps must be caught in review.
