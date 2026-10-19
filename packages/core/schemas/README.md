# schemas/

The published JSON Schemas for the files that METIS packages share. Each file is generated from a
Pydantic model in `metis-core`, so that any package can read the file it describes.
All future shared file contracts belong in core. Published `*.schema.json` files belong
in this directory. Private runtime models and API request and response models stay in
their owning packages.

- `specification.schema.json` describes `specification.yaml`. The wizard writes this file, and
  the engine runs it. Schema-aware editors and YAML validators use the schema for autocomplete
  and inline validation.

The JSON files here are **auto-generated**. Do not edit them directly; they will be overwritten.

## Source of truth

| Schema file | Pydantic model | Version constant | Source file |
|---|---|---|---|
| `specification.schema.json` | `SpecificationDocument` | `_SPECIFICATION_VERSION` | `src/metis/core/specification.py` |

The specification schema requires `schema_version`, `id`, and `runner_factory_ref`. In memory, these keys have
defaults, so an incomplete Interview draft still loads. `Specification.model_dump()` always writes
the three keys, so every file that the wizard saves conforms to the schema. The engine also refuses
a file without them.

The specification schema describes the document shape only. The engine also checks references, IDs, Grader
settings, and the runner when it loads the file (`Specification.execution_errors()` and
`metis.engine.simulation.types.Specification`).

`TrialRecord` (`metis.core.trials`) is code-produced and has no standalone schema file. Its version constant is
`_TRIAL_RECORD_VERSION` in `packages/engine/src/metis/engine/simulation/types.py`.

`EvaluationResults` (`outputs/reports/results.json`, defined in `metis.core.reporting`) is
the current engine output. It has a `records` list and no published schema file.
The current Insights CLI reads private legacy models in `metis.insights._legacy_results`,
with `turn_results` and `session_results`. It rejects the current engine format until
[#454](https://github.com/govtech-responsibleai/metis/issues/454) is complete.

`Report` in `metis.core.report` defines `outputs/reports/report.json` and has no
published schema file. The report writer validates data through this model.
Saved reports contain `"schema_version": 2`. `Report` defaults a missing version to `2`.
Its `Literal[2]` field rejects other explicit values, including `null`.

## How to add a shared schema

Shared file contracts need a core Pydantic model. Publish a JSON Schema when an
editor or external consumer needs to validate data without importing METIS.
For a published schema, follow these steps.

1. Define the shared file model in `packages/core/src/metis/core/`.
2. Add a `schema_version` field and a version constant. Define how missing and unsupported
   versions are handled. Follow the `next` exception below while it applies.
3. Register the model, filename, version, and alias setting in `_MODELS` in
   `packages/core/scripts/generate_schema.py`.
4. Run `make -C packages/core generate-schema`. Commit the generated file in this directory.
5. Test the file writer and reader. Update this guide and the file contract documentation.
6. Run `make -C packages/core check-schema` and the relevant tests.

## How to modify a schema

1. Edit the model. For the specification, edit Profile fields in `src/metis/core/profile.py`,
   Experiment fields in `src/metis/core/experiment.py`, or the flat document in
   `src/metis/core/specification.py`.
2. Check the [Version bump rules](#version-bump-rules), including the `next` exception.
   After graduation, a breaking change requires an increment to the `_*_VERSION` constant
   and the matching `Literal[N]` annotation on `schema_version`.
3. Run `make -C packages/core generate-schema` to regenerate the schema files
4. Update `packages/engine/example-experiment/specification.yaml` if the specification model changed
5. Commit the updated schema file alongside the model change; note any version bump in the commit message

## Automated checks

`make -C packages/core check-schema` runs in CI (`make ci`). It uses the same model
registry as generation. It fails for missing or stale schemas, unregistered schemas in
core, and published schemas outside core. It checks tracked and non-ignored untracked
`*.schema.json` files through Git. Ignored dependencies and caches are excluded.
These tests run in `make test`:

- `tests/unit/core/test_specification_schema.py` fails if the specification schema is stale, if
  the example specification doesn't validate against it, or if a written draft doesn't validate
  against it.
- `tests/unit/insights/test_cli_report.py` checks that a real CLI run writes version `2`,
  validates the output, and rejects unsupported report versions. It needs no sample file.
- `tests/unit/core/test_schema_check.py` checks schema ownership and registration.
- `tests/unit/engine/test_specification_execution.py` checks that the runnable example
  (`packages/engine/example-experiment/simple/specification.yaml`) loads for execution.

These checks catch forgotten regeneration runs and broken examples, but **not** forgotten version bumps — if you make a breaking change and don't increment the `_*_VERSION` constant, the tests won't notice.

## Version bump rules

During the `next` pre-release phase, schema versions stay at `2`. Record breaking changes
in `MIGRATION.md` and `CHANGELOG.next.md`. Do not increment the schema version for each
change. See [the version policy](../../../docs/version-maintenance.md).
The rules below apply after graduation.

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
- `TrialConfig`, `TrialOutcome`, `TrialFailure`, `Artifact` → bump `TrialRecord`
- Report nodes such as `Trial`, `Criterion`, and `ResultTable` → bump `Report`

The common trap is giving a breaking field a default to avoid a bump. That's fine for genuinely optional fields, but if the field is semantically required and you're using a default as a workaround, you're hiding a real schema change. Use a bump and a migration instead.

Versions are integers (1, 2, 3, ...), not semver. A single integer means: "if this doesn't match what you expect, you cannot parse this." There is no "minor" — additive changes are invisible to consumers by design. The version is independent of the package version.

## FAQ

### Do we reject v1 data once we're on v2?

**Yes, for explicit unsupported versions.** `Report` uses its `Literal[2]` field for
this check. A missing report version defaults to `2`. Other contracts, including
`EvaluationResults` and `TrialRecord`, also use `_check_version` validators. The
specification draft model supplies defaults; execution validation requires a version.

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

These strategies are needed to load files with an explicit unsupported version.

### Who is responsible for updating files after a bump?

For **user-authored inputs** (`specification.yaml`): the user must update their files. The validator gives a clear error message. This is a deliberate one-time migration cost — the alternative (silent default-filling of a required field) would make the version field meaningless.

For **code-produced outputs** (`record.json` session records): the harness always writes `schema_version` explicitly, so new records are always stamped correctly. Old records from a previous run will not load after a bump — use one of the coexistence strategies above if needed.

### Is version bumping enforced automatically?

Not fully — see [Automated checks](#automated-checks) above for what CI catches. Forgotten version bumps must be caught in review.
