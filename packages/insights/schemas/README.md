# schemas/

`report.schema.json` is generated from the Pydantic `Report` model in
`src/metis/insights/_models.py` (version constant `_REPORT_VERSION`). It is the published
contract for `reports/report.json`, the file `metis insights report` writes. Downstream
consumers validate report files against it.

The file is **auto-generated**. Do not edit it; run `make -C packages/insights generate-schema`
after changing the model and commit the result with the change. `make ci` runs
`make -C packages/insights check-schema`, which fails when the committed file is stale.

The version-bump rules are the same as for the engine's schemas; see
[`packages/engine/schemas/README.md`](../../engine/schemas/README.md#version-bump-rules).

`EvaluationResults` (`reports/results.json`, defined in `metis.core.reporting`) is the
input to this package. It is code-produced and has no published schema file.
