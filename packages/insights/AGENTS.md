# metis-insights

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Report generation for evaluation outputs. `metis insights report --results-file <path>`
reads legacy `outputs/reports/results.json` files and produces the
terminal pass/fail/skip summary plus `outputs/reports/report.json` and `outputs/reports/report.html`.

## Dependency Rule

Depends on `metis-core` only. Never import `metis.engine`, `metis.library`, or
`metis.wizard`; `tests/unit/insights/test_dependency_boundary.py` fails if source here
does. Insights still reads `results.json` version 2, through a private copy of the old
models in `_legacy_results.py`. The engine now writes a new format
(`metis.core.reporting`), so `metis insights report` exits with the message "This
results.json uses the new GraderRecord format (grader redesign #428), which metis insights
report cannot read yet. Rerun the report once #454 is released." until its redesign
(#454) moves it onto the new types.
`Report`, the `report.json` contract, lives in `metis.core.report` so that other packages
can read reports.

## Layout

- `cli.py` — the Typer app (`metis insights …`)
- `report.py` — `format_terminal_summary`, `save_report`
- `_report.py` — `build_report`, `load_report_sources` (the behaviour/criterion rollup)
- `_aggregation.py`, `_report_page.py`, `_report_styles.py` — summary counts and HTML

## Report contract

`metis.core.report.Report` defines and validates `report.json`. Reports contain
`schema_version: 2`. The model defaults a missing version to `2` and rejects other
explicit versions. There is no published JSON Schema file for reports.

The report's content rules live in [docs/guide/report.md](../../docs/guide/report.md).
