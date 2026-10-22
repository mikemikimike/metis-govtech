# Example Experiment

`simple/` is a ready-to-run experiment input for `metis engine run`: one Persona, one
Scenario, one Task, one Trial, and one Grader, with no uploaded files.

**It is written for Orca**, so it needs Orca, user-agent model, and Langfuse credentials.
Evaluating a different system will require writing your own specification.

## Structure

```
example-experiment/
├── simple/
│   ├── specification.yaml
│   └── fixtures/
└── targets/              # An example target binding for the generic HTTP runner
    └── orca-api.yaml
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

## Binding another API

`targets/orca-api.yaml` is an example *target binding*: it lets the generic HTTP runner
drive Orca's REST API from a YAML file, with no Python runner. To use it, name it in a
specification:

```yaml
runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
target_binding: targets/orca-api.yaml
```

The [simple specification](simple/specification.yaml) does not do so; it uses the Orca
runner above. The [`gen_2` README](../src/metis/engine/simulation/gen_2/README.md)
explains each field and how to write one for your own app. The runner has been tried on
Orca's API only.

## A larger example

The complete Orca specification (18 Tasks, 54 Trials, and the fixture files it uploads) lives
with the Wizard testbed at
[`packages/testbed/wizard/cases/orca/outputs/`](../../testbed/wizard/cases/orca/outputs/).

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
