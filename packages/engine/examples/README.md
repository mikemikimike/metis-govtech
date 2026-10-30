# Examples

`http-agentic_eval_toyapp-1/` is a ready-to-run experiment input for `metis engine run`. It
needs the toy app running, plus user-agent and runner-agent model credentials. Evaluating a
different system requires writing your own specification. `browser-chat-1/` holds only a
template binding, so it is not runnable on its own.

Folder names say how the example runs: `{http|browser}-{target}-{variant}`. The first part
is the generic runner for that transport, driven by a target binding file. `http` calls the
target's API (`HttpRunnerFactory`); `browser` drives its web page (`BrowserRunnerFactory`).
The target is the system under test (`agentic_eval_toyapp`, `chat`), and the variant number
tells apart different experiments with the same transport and target.

| Folder | What it shows | Runner |
|---|---|---|
| [`http-agentic_eval_toyapp-1/`](http-agentic_eval_toyapp-1/specification.yaml) | The generic HTTP runner on a small app, with an experiment designed in the Wizard's Interview: three Tasks (a concise annual-leave answer, an expense question with missing details, and a question the policy collection cannot answer) put to the [agentic-eval toy app](https://github.com/govtech-responsibleai/agentic-eval-toyapp), and ten LLM-judged Criteria (`CriterionJudgeGrader`) across four Behaviours. It runs one Trial per Task so that a first run is quick. Its binding, [`toyapp-api.yaml`](http-agentic_eval_toyapp-1/toyapp-api.yaml), has no auth and no advice: it names the app and where its OpenAPI document is. Start the app and set `TOYAPP_API_URL` (for example `http://127.0.0.1:8000`) first. | `HttpRunnerFactory` |
| [`browser-chat-1/`](browser-chat-1/web-chat.yaml) | A template target binding for a chat app that has only a web page, for the generic browser runner. It has no specification or fixtures: the URL, secret names and sign-in steps in it are made up, so change them for your app. The runner has never met a live page. | `BrowserRunnerFactory` |

## Structure

```
examples/
├── browser-chat-1/
│   └── web-chat.yaml          # a template binding, with no specification
└── http-agentic_eval_toyapp-1/
    ├── specification.yaml
    ├── toyapp-api.yaml        # the target binding, beside the specification
    └── fixtures/
```

## Running

From the repository root, with the toy app running and the model credentials set:

```bash
# Simulate, evaluate, and write results.
uv run metis engine run --input-dir packages/engine/examples/http-agentic_eval_toyapp-1/

# Separate phases: simulate prints the evaluate command for the output it wrote.
# The --experiment-dir value is that output directory. Its real name holds the
# experiment id and the start time of the run.
uv run metis engine simulate --input-dir packages/engine/examples/http-agentic_eval_toyapp-1/
uv run metis engine evaluate --experiment-dir experiments/execute/toyapp-http-simple-20260820-143000/
```

`run` writes `outputs/reports/results.json` (holding one GraderRecord per grader per session)
under the new `experiments/execute/toyapp-http-simple-<timestamp>/` directory and prints the
`metis insights report` command that builds a report from it.

Simulation uses the live TUI in a terminal. Use `--no-tui` to turn it off. Evaluation uses a
normal progress bar, has no TUI option, and writes one complete `logs/evaluate.log` file in
the named output.

## Binding another API

`http-agentic_eval_toyapp-1/` shows how an experiment uses a target binding. Its
specification names the generic HTTP runner and the binding file next to it:

```yaml
runner_factory_ref: metis.engine.simulation.runners.http.HttpRunnerFactory
target_binding: toyapp-api.yaml
```

The path is relative to the specification and must stay inside the experiment folder, so each
experiment keeps its own copy of the binding. The
[simulation README](../src/metis/engine/simulation/README.md) explains each field and how
to write a binding for your own app. The toy app is the only target the runner has been
tried on, and this example has not been run yet.

See the [engine guide](../../../docs/guide/engine.md) for setup and runner details.
