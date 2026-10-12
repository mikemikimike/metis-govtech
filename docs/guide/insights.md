# metis-insights

`metis insights report` turns the grader results of one evaluation into the product
evaluation report. It is the step after `metis engine evaluate` (or `run`), which scores
the traces and writes `reports/results.json` but builds no report.

## Usage

```bash
metis insights report --results-file experiments/orca-eval-20260730-143022/reports/results.json
```

`evaluate` and `run` print this exact command, with the path already filled in, at the
end of their summary. The standalone `metis-insights report --results-file <path>`
behaves the same.

| Flag | Meaning |
|---|---|
| `--results-file PATH` | The `results.json` that evaluation wrote. A relative path resolves against the current directory. |

## What it reads and writes

The command climbs from the results file to its experiment directory (two levels up),
reads the frozen inputs and trial records there, and writes the report back beside the
results:

```
experiments/orca-eval-20260730-143022/
├── inputs/specification.yaml   # read: Features, Behaviours, Criteria
├── trials/*/record.json        # read: personas and trial outcomes
└── reports/
    ├── results.json            # read: written by metis engine evaluate
    ├── report.json             # written: machine-readable report
    └── report.html             # written: visual report (open in a browser)
```

Keep `results.json` inside its experiment's `reports/` directory. Run again after a new
evaluation and the report files are overwritten.

It also prints the terminal pass/fail/skip table per Criterion.

## Outcomes

- **Report written.** Exit code 0, and the paths of both files are printed.
- **No specification.** When `inputs/specification.yaml` is missing or unreadable, the
  summary still prints, the command says which path it looked for, and it exits 0. A run
  without a product specification opts out of the report.
- **Unreadable results.** A missing file, malformed JSON, or a `results.json` written by
  a different version of metis-engine (`Unsupported schema_version …`) exits 1 and
  writes nothing. Re-run `metis engine evaluate` to produce a current file.

The report's content — scoring, statuses, and failure evidence — is defined in the
[report contract](report.md), and its JSON shape in the
[report JSON Schema](../../packages/insights/schemas/report.schema.json).
