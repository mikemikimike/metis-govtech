# Example Experiment

`simple/` is a ready-to-run experiment input for `metis engine run`: one Persona, one
Scenario, one Task, one Trial, and one Grader, with no uploaded files.

**It is written for Orca**, so it needs Orca, user-agent model, and Langfuse credentials.
Evaluating a different system will require writing your own specification.

## Structure

```
example-experiment/
└── simple/
    ├── specification.yaml
    └── fixtures/
```

## Running

The [simple specification](simple/specification.yaml) runs one direct question through
Orca's API. Its Grader, `DemoTraceBudgetGrader`, checks that the session used at most four
traces (persona–target exchanges). The Task shows the optional execution settings, including
the separate turn limit and retry count.

From the repository root, with Orca, user-agent model, and Langfuse credentials set:

```bash
# Simulate, evaluate, and write results.
uv run metis engine run --input-dir packages/engine/example-experiment/simple/

# Separate phases: simulate prints the evaluate command for the output it wrote.
# The --experiment-dir value is that output directory. Its real name holds the
# experiment id and the start time of the run.
uv run metis engine simulate --input-dir packages/engine/example-experiment/simple/
uv run metis engine evaluate --experiment-dir experiments/execute/orca-simple-20260820-143000/
```

`run` writes `outputs/reports/results.json` (holding one GraderRecord per grader per session)
under the new `experiments/execute/orca-simple-<timestamp>/` directory and prints the
`metis insights report` command that builds a report from it.

Simulation uses the live TUI in a terminal. Use `--no-tui` to turn it off. Evaluation uses a
normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in
the named output.

## A larger example

The complete Orca specification (18 Tasks, 54 Trials, and the fixture files it uploads) lives
with the Wizard testbed at
[`packages/testbed/wizard/cases/orca/outputs/`](../../testbed/wizard/cases/orca/outputs/).

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
