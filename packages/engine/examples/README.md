# Examples

Each folder here is a ready-to-run experiment input for `metis engine run`. The `orca-` ones
are written for Orca and need Orca, user-agent model, and Langfuse credentials; the toy app
one needs the toy app running instead of Orca. Evaluating a different system requires writing
your own specification.

| Folder | What it shows | Runner |
|---|---|---|
| [`orca-api-simple1/`](orca-api-simple1/specification.yaml) | The smallest complete experiment: one Persona, one Scenario, one Task, one Trial, and one Grader, with no uploaded files. The persona asks Orca a direct question, and `DemoTraceBudgetGrader` checks that the session used at most four traces (persona–target exchanges). The Task also shows the optional execution settings, including the separate turn limit and retry count. | `OrcaApiRunnerFactory` |
| [`orca-api-simple2/`](orca-api-simple2/specification.yaml) | An experiment with a fixture file. The persona uploads `q3_sales.csv` and asks for an analysis with constraints, so the run exercises file upload and a longer session. One Behaviour, "Chart quality", is graded with `DemoTraceBudgetGrader`. | `OrcaApiRunnerFactory` |
| [`orca-api-http-simple1/`](orca-api-http-simple1/specification.yaml) | The same question as `orca-api-simple1`, run through the generic HTTP runner instead of a Python runner. [`orca-api.yaml`](orca-api-http-simple1/orca-api.yaml) is a *target binding*: it tells the runner where Orca's OpenAPI document is, which calls are forbidden and how to authenticate, with no code. | `HttpRunnerFactory` |
| [`agentic-eval-toyapp-simple1/`](agentic-eval-toyapp-simple1/specification.yaml) | The generic HTTP runner on a second app, with an experiment designed in the Wizard's Interview: three Tasks (a concise annual-leave answer, an expense question with missing details, and a question the policy collection cannot answer) put to the [agentic-eval toy app](https://github.com/govtech-responsibleai/agentic-eval-toyapp), and ten LLM-judged Criteria (`CriterionJudgeGrader`) across four Behaviours. It runs one Trial per Task so that a first run is quick. Its binding, [`toyapp-api.yaml`](agentic-eval-toyapp-simple1/toyapp-api.yaml), has no auth and no advice: it names the app and where its OpenAPI document is. Start the app and set `TOYAPP_API_URL` (for example `http://127.0.0.1:8000`) first. | `HttpRunnerFactory` |

## Structure

```
examples/
├── orca-api-simple1/
│   ├── specification.yaml
│   └── fixtures/
├── orca-api-simple2/
│   ├── specification.yaml
│   └── fixtures/q3_sales.csv
├── orca-api-http-simple1/
│   ├── specification.yaml
│   ├── orca-api.yaml          # the target binding, beside the specification
│   └── fixtures/
└── agentic-eval-toyapp-simple1/
    ├── specification.yaml
    ├── toyapp-api.yaml
    └── fixtures/
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

`orca-api-http-simple1/` shows how an experiment uses a target binding. Its specification
names the generic HTTP runner and the binding file next to it:

```yaml
runner_factory_ref: metis.engine.simulation.gen_2.runners.http.HttpRunnerFactory
target_binding: orca-api.yaml
```

The path is relative to the specification and must stay inside the experiment folder, so each
experiment keeps its own copy of the binding. The
[`gen_2` README](../src/metis/engine/simulation/gen_2/README.md) explains each field and how
to write a binding for your own app. The runner has been tried on Orca's API only. The toy
app example is its second target and has not been run yet.

## A larger example

The complete Orca specification (18 Tasks, 54 Trials, and the fixture files it uploads) lives
with the Wizard testbed at
[`packages/testbed/wizard/cases/orca/outputs/`](../../testbed/wizard/cases/orca/outputs/).

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
