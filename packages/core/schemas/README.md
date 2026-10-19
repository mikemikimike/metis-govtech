# Published schemas

`specification.schema.json` describes `specification.yaml` for editors and external
validators. It is generated from `SpecificationDocument` in
[`metis.core.specification`](../src/metis/core/specification.py). Do not edit the JSON file.

New shared file models belong in core. Publish a JSON Schema only when an editor or
external consumer needs one. Store published schemas here. Private runtime and API
models stay in their owning packages.

`Report` and `EvaluationResults` are core Pydantic models. They have no published
JSON Schema files.

## Update a schema

1. Edit the core model. For a new published schema, add it to `_MODELS` in
   [`scripts/generate_schema.py`](../scripts/generate_schema.py).
2. Run these commands from the repository root:

   ```bash
   make -C packages/core generate-schema
   make -C packages/core check-schema
   ```

3. Update affected examples and tests. Commit the model and generated schema together.

CI checks for missing or stale schemas, unregistered schemas, and schemas outside core.
The Specification schema requires `schema_version`, `id`, and `runner_factory_ref`.
In-memory drafts can use defaults. Engine execution adds validation of references and settings.

## Version policy

On `next`, keep schema versions at `1`. Record breaking changes in `MIGRATION.md`
and `CHANGELOG.next.md`.

After graduation, a change that prevents valid existing data from loading requires a
version bump. Update the root model's version constant and `Literal` field, including
when the breaking change is in a nested model. CI does not detect missing version bumps.
See the [version policy](../../../docs/version-maintenance.md).
