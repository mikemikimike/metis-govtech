# metis-insights

`metis insights report` turns the grader results of one evaluation into the target
evaluation report. It is the step after `metis engine evaluate` (or `run`), which scores
the traces and writes `outputs/reports/results.json` but builds no report.

## Usage

```bash
metis insights report --results-file experiments/execute/orca-eval-20260730-143022/outputs/reports/results.json
```

`evaluate` and `run` print this exact command, with the path already filled in, at the
end of their summary. The standalone `metis-insights report --results-file <path>`
behaves the same.

| Flag | Meaning |
|---|---|
| `--results-file PATH` | The `results.json` that evaluation wrote. A relative path resolves against the current directory. |

## What it reads and writes

The command finds the execution root from the `outputs/reports/` path. It reads
the input snapshot and trial records, then writes reports beside the results:

```text
experiments/execute/orca-eval-20260730-143022/
├── inputs/specification.yaml
└── outputs/
    ├── trials/*/record.json
    └── reports/
        ├── results.json
        ├── report.json
        └── report.html
```

Keep `results.json` inside its experiment's `outputs/reports/` directory. Run again after a new
evaluation and the report files are overwritten.

It also prints the terminal pass/fail/skip table per Criterion.

## Outcomes

- **Report written.** Exit code 0, and the paths of both files are printed.
- **No specification.** When `inputs/specification.yaml` is missing or unreadable, the
  summary still prints, the command says which path it looked for, and it exits 0. A run
  without a target specification opts out of the report.
- **Invalid results location.** A results file outside `outputs/reports/` exits 1.
  Keep the execution folder together when you move it.
- **Unreadable results.** A missing file, malformed JSON, or a `results.json` written by
  a different version of metis-engine (`Unsupported schema_version …`) exits 1 and
  writes nothing. Re-run `metis engine evaluate` to produce a current file. The current
  `metis engine evaluate` writes a format using GraderRecord that this command does not
  read yet (#454).

The report's content — scoring, statuses, and failure evidence — is defined in the
[report contract](report.md), and its JSON shape in the
core [Report model](../../packages/core/src/metis/core/report.py).
