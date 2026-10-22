# Examples

Each folder here is a ready-to-run experiment input for `metis engine run`, except `targets/`,
which holds a target binding that an experiment can name. All of them are written for Orca, so
they need Orca, user-agent model, and Langfuse credentials. Evaluating a different system
requires writing your own specification.

| Folder | What it shows | Runner |
|---|---|---|
| [`orca-api-simple1/`](orca-api-simple1/specification.yaml) | The smallest complete experiment: one Persona, one Scenario, one Task, one Trial, and one Grader, with no uploaded files. The persona asks Orca a direct question, and `DemoTraceBudgetGrader` checks that the session used at most four traces (persona–target exchanges). The Task also shows the optional execution settings, including the separate turn limit and retry count. | `OrcaApiRunnerFactory` |
| [`orca-api-simple2/`](orca-api-simple2/specification.yaml) | An experiment with a fixture file. The persona uploads `q3_sales.csv` and asks for an analysis with constraints, so the run exercises file upload and a longer session. One Behaviour, "Chart quality", is graded with `TraceBudgetGrader`. | `OrcaApiRunnerFactory` |
| [`targets/orca-api.yaml`](targets/orca-api.yaml) | A *target binding*: it lets the generic HTTP runner drive Orca's REST API from a YAML file, with no Python runner. | none yet; see below |

## Structure

```
examples/
├── orca-api-simple1/
│   ├── specification.yaml
│   └── fixtures/
├── orca-api-simple2/
│   ├── specification.yaml
│   └── fixtures/q3_sales.csv
└── targets/
    └── orca-api.yaml
```

## Running

From the repository root, with Orca, user-agent model, and Langfuse credentials set:

```bash
# Simulate, evaluate, and write results.
uv run metis engine run --input-dir packages/engine/examples/orca-api-simple1/

# Separate phases: simulate prints the evaluate command for the output it wrote.
# The --experiment-dir value is that output directory. Its real name holds the
# experiment id and the start time of the run.
uv run metis engine simulate --input-dir packages/engine/examples/orca-api-simple1/
uv run metis engine evaluate --experiment-dir experiments/execute/orca-simple-20260820-143000/
```

`run` writes `outputs/reports/results.json` (holding one GraderRecord per grader per session)
under the new `experiments/execute/orca-simple-<timestamp>/` directory and prints the
`metis insights report` command that builds a report from it.

Simulation uses the live TUI in a terminal. Use `--no-tui` to turn it off. Evaluation uses a
normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in
the named output.

## Binding another API

`targets/orca-api.yaml` is an example target binding. To use it, name it in a specification:

```yaml
runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
target_binding: targets/orca-api.yaml
```

The path is relative to the specification and must stay inside the experiment folder, so an
experiment keeps its own `targets/` folder rather than reaching into this one. Neither Orca
example above does this today. The [`gen_2` README](../src/metis/engine/simulation/gen_2/README.md)
explains each field and how to write a binding for your own app. The runner has been tried on
Orca's API only.

## A larger example

The complete Orca specification (18 Tasks, 54 Trials, and the fixture files it uploads) lives
with the Wizard testbed at
[`packages/testbed/wizard/cases/orca/outputs/`](../../testbed/wizard/cases/orca/outputs/).

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
