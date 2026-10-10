# metis-insights

See root [AGENTS.md](../../AGENTS.md) for monorepo-wide instructions.

## Package Purpose

Report generation for evaluation outputs. `metis insights report --results-file <path>`
reads the `reports/results.json` that `metis engine evaluate` writes and produces the
terminal pass/fail/skip summary plus `reports/report.json` and `reports/report.html`.

## Dependency Rule

Depends on `metis-core` only. Never import `metis.engine`, `metis.library`, or
`metis.wizard`; `tests/unit/insights/test_dependency_boundary.py` fails if source here
does. Shared input types (`EvaluationResults`, `TurnReport`, `SessionReport`) live in
`metis.core.reporting` because both engine and insights need them.

## Layout

- `cli.py` — the Typer app (`metis insights …`)
- `report.py` — `format_terminal_summary`, `save_report`
- `_report.py` — `build_report`, `load_report_sources` (the behaviour/criterion rollup)
- `_models.py` — `Report`, the `report.json` contract
- `_aggregation.py`, `_report_page.py`, `_report_styles.py` — summary counts and HTML

## Schema Sync

`_models.py` is the source of truth for `schemas/report.schema.json`. After changing it:

```bash
make -C packages/insights generate-schema
```

The report's content rules live in [docs/guide/report.md](../../docs/guide/report.md).
