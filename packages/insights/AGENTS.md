# metis-insights

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Report generation for evaluation outputs. `metis insights report --results-file <path>`
reads legacy `outputs/reports/results.json` files and produces the
terminal pass/fail/skip summary plus `outputs/reports/report.json` and `outputs/reports/report.html`.

## Dependency Rule

Depends on `metis-core` only. Never import `metis.engine`, `metis.library`, or
`metis.wizard`; `tests/unit/insights/test_dependency_boundary.py` fails if source here
does. Insights reads both legacy version 1 results and core `EvaluationResults` records.
`_results.py` validates each input format and projects recorded outcomes for the report.
Preserve recorded Criterion IDs, grader settings, and Task and Trial identity.
Keep grader errors separate from target failures and skips. Exclude errors and skips
from pass rates. New records have no trace or turn identity.


## Layout

- `cli.py` — the Typer app (`metis insights …`)
- `report.py` — `format_terminal_summary`, `save_report`
- `_models.py` — `Report`, the `report.json` contract
- `_report.py` — `build_report`, `load_report_sources` (the behaviour/criterion rollup)
- `_aggregation.py`, `_report_page.py`, `_report_styles.py` — summary counts and HTML

## Report contract

`_models.Report` defines and validates `report.json`. `metis.insights` re-exports it. Reports contain
`schema_version: 1`. The model defaults a missing version to `1` and rejects other
explicit versions. There is no published JSON Schema file for reports. `Report` stays in
insights while no other package reads `report.json`. Move it to core when a second package
needs it.

The report's content rules live in [docs/guide/report.md](../../docs/guide/report.md).
