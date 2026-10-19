# Engine User Guide

## Introduction

metis-engine is the evaluation runtime for METIS. It drives a target through a runner using LLM-powered simulated user personas. Orca runners support its API and browser UI. It then extracts the resulting traces from Langfuse, runs configurable evaluation graders, and writes their results for [`metis insights report`](insights.md) to turn into a report. Simulation and evaluation are separate commands, with `run` available for the combined flow.

This guide is for anyone setting up evaluations against a web-based agentic system. By the end, you will have:

- A working local installation
- A completed evaluation run using the bundled example experiment
- The knowledge to write your own experiments with custom personas, scenarios, and graders

For the overall METIS architecture and other packages, see the [project README](../../README.md).

---

## Prerequisites & Setup

### Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (workspace and package manager)
- GNU Make

### Install

From the monorepo root:

```bash
make install          # install everything

make install-engine   # install only engine dependencies (includes Playwright)
```

`make install` installs all workspace dependencies but not Playwright. If you select the browser runner, also install the Playwright extra — `make install-engine` already includes it:

```bash
make install-extras-playwright
```

### Environment Configuration

Copy the example environment file and fill in your credentials:

```bash
cp packages/engine/.env.example .env
```

Set Langfuse and OpenAI credentials, plus the credentials for your selected Orca runner:

| Group | Variables | Purpose |
|-------|-----------|---------|
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Trace storage and retrieval |
| OpenAI | `OPENAI_API_KEY` | Powers the simulated user agent, and model-based graders unless `JUDGE_*` is set |
| Judge | `JUDGE_API_KEY`, `JUDGE_BASE_URL` | Optional gateway for grader LLM calls; falls back to `OPENAI_*` |
| Orca API runner | `ORCA_API_URL`, `ORCA_API_KEY` | Target URL and API key for the example experiment |
| Orca browser runner | `ORCA_URL`, `ORCA_USERNAME`, `ORCA_PASSWORD` | Target URL and login credentials when selecting the browser runner |

Optional tuning variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_AGENT_MODEL` | `gpt-5.6-luna` | Model used for the simulated user persona |
| `USER_AGENT_MAX_TOKENS` | _(unset)_ | Max tokens per user agent response; unset/empty → parameter omitted, provider default applies. Set explicitly (e.g. `4096`) for reasoning models where chain-of-thought tokens count against the limit |
| `USER_AGENT_TEMPERATURE` | _(unset)_ | Sampling temperature for the user agent; unset/empty → parameter omitted, provider default applies |
| `JUDGE_MODEL` | `gemini-3.5-flash-lite` | Judge model when neither the criterion nor `defaults.judge_model` sets one |
| `HEADED` | `false` | Set to `true` to show the browser window |

### Verify Installation

```bash
metis engine run --help
```

You should see the run command's help text with all available flags.

---

## Quick Start

Run the bundled example experiment to verify everything works end-to-end.

### The Example Experiment

The directory `packages/engine/example-experiment/` contains a complete experiment definition written for Orca. The personas, task descriptions, fixture files, and grader selections assume Orca's specific multi-agent architecture.

```
example-experiment/
├── specification.yaml   # Complete evaluation specification
├── simple/              # One Task, one Trial, one Grader, no uploaded files
└── fixtures/            # Files uploaded during simulation
    ├── q3_sales.csv
    ├── q3_sales_corrupted.csv
    ├── q3_sales_v1.csv
    ├── q3_sales_v2.csv
    └── policy_document_adversarial.txt
```

### Run It

The commands below use `example-experiment/simple/`. The full example does not run yet: only one
of its Criteria names a grader, so the engine refuses it at validation (see the example's README).

```bash
metis engine run --input-dir packages/engine/example-experiment/simple/
```

To run the phases separately, use `simulate` first. It prints the exact `evaluate` command for the output directory it created. `evaluate` scores the directory that you name:

```bash
metis engine simulate --input-dir packages/engine/example-experiment/simple/
metis engine evaluate --experiment-dir experiments/execute/orca-eval-20260820-143000/
```

`experiments/execute/orca-eval-20260820-143000/` is the output directory that `simulate` created. The name is only a sample: `simulate` makes the real name from the experiment `id` and the start time of the run, so use the path that `simulate` printed.

If simulation stops before all runs finish, continue the output directory that you name. `simulate` prints this exact command, so you never retype a timestamp:

```bash
metis engine simulate --resume --experiment-dir experiments/execute/orca-eval-20260820-143000/
# or run the remaining simulation and then evaluate everything:
metis engine run --resume --experiment-dir experiments/execute/orca-eval-20260820-143000/
```

Resume reads the experiment and the fixtures from the frozen `inputs/` snapshot in the named directory, not from the source directory. It retries only missing, invalid, or `system_error` records, and appends to the experiment-level simulation log. Extra run folders are ignored. A valid record is complete even if an artifact file is missing. Passing `--resume` with `--input-dir` is an error: the message lists the outputs that exist for the experiment `id` and names the correct flag.

### What You'll See

The engine launches a Simulation TUI for simulation:

- Progress bars for each Task
- Per-run status (`pending → simulating → done/failed`)
- A scrolling log tail with recent events

Evaluation uses a normal, non-full-screen progress bar:

- One completed/total count for run records
- The current record and phase (`extracting` or `evaluating`)
- Failed records advance the bar after the warning is shown

The combined `run` command closes the Simulation TUI before it starts the evaluation progress bar. It performs four phases:

1. **Simulate** — the user agent interacts with Orca through the selected runner
2. **Extract** — traces are fetched from Langfuse
3. **Evaluate** — graders score the extracted traces
4. **Results** — grader results are written to `outputs/reports/results.json`; build the report with [`metis insights report`](insights.md)

### Where Results Land

Each execution produces output in `experiments/execute/<id>-<timestamp>/`. The `outputs/reports/` directory is created by `evaluate` or `run`, which write `results.json`; `metis insights report` adds `report.json` and `report.html`. Simulation-only runs stop after `outputs/trials/` and `logs/`:

```text
experiments/execute/orca-eval-20260730-143022/
├── inputs/
│   ├── specification.yaml
│   └── fixtures/
├── outputs/
│   ├── trials/
│   │   └── TC-001-cooperative-delegator-1/
│   │       ├── record.json
│   │       ├── simulate.log       # Link to the trial log
│   │       └── artifacts/
│   │           ├── run-manifest.json
│   │           └── ...
│   └── reports/
│       ├── results.json           # Engine evaluation
│       ├── report.json            # Insights
│       └── report.html            # Insights
└── logs/
    ├── simulate.log
    ├── simulate-TC-001_cooperative-delegator-01.log
    └── evaluate.log
```

`results.json` holds one GraderRecord per grader per session, each with one result per grading scope. `metis insights report` does not read this format yet (#454).

The structure of `report.json` is defined by a [JSON Schema](../../packages/core/schemas/report.schema.json). Downstream consumers can validate report files against this schema programmatically using any JSON Schema validator.

Use `logs/evaluate.log` to review extraction, each criterion's grader and resolved arguments (including the judge model), every recorded result with its outcome, score and reason, soft failures, hard failures, and final record counts for the latest evaluation attempt.

See the [report contract](report.md) for the report's scoring,
status, failure-evidence, and information-architecture rules.

### Debugging Tip

For the browser runner, set `HEADED=true` to show the browser window. The bundled example selects the API runner. To use the browser runner, set `runner_factory_ref` to `metis.engine.simulation.runners.orca_playwright.OrcaPlaywrightRunnerFactory` and supply its credentials:

```bash
HEADED=true metis engine simulate --input-dir packages/engine/example-experiment/simple/
```

---

## Experiment Configuration

An experiment is defined by a single `specification.yaml` file placed alongside a `fixtures/` directory:

```
my-experiment/
├── specification.yaml
└── fixtures/
    └── my-data.csv
```

### Top-Level Fields

```yaml
schema_version: 2

id: my-evaluation
runner_factory_ref: metis.engine.simulation.runners.orca_api.OrcaApiRunnerFactory
target:
  name: Orca
  users: Programme managers and analysts.
  description: Evaluate routing and analysis capabilities.
```

| Field | Required | Description |
|-------|----------|-------------|
| `schema_version` | Yes | Always `2` (current version) |
| `id` | Yes | Identifier used in the output directory name |
| `runner_factory_ref` | Yes | Importable RunnerFactory class |
| `target` | Yes | Target name, users, description, and optional detail |
| `features` | Yes for execution | Features, Behaviours, and Criteria to measure |
| `personas` | Yes for execution | User types selected by Tasks |
| `scenarios` | Yes for execution | Situations selected by Tasks |
| `tasks` | Yes for execution | Test Cases with explicit references |
| `fixture_content_descriptions` | No | Map of fixture filenames to content descriptions |

### Personas

Personas are LLM-powered simulated users. During simulation, each persona interacts with the target according to its behavioral profile — communication style, patience level, domain expertise, and goals.

```yaml
personas:
  - id: cooperative-delegator
    name: Cooperative delegator
    description: >
      A mid-level programme manager who is comfortable with AI tools, has time
      to engage, and communicates in a friendly, conversational way. They
      disclose information eagerly and cooperate fully, with a moderate
      frustration threshold.

  - id: impatient-executive
    name: Impatient executive
    description: >
      A time-poor senior director who delegates everything and expects systems
      to just work. They communicate in curt bullet points with no pleasantries
      and have a very low frustration threshold.
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier, referenced by Tasks |
| `name` | Yes | Human-readable Persona name |
| `description` | Yes | Behavioral profile the LLM user agent embodies |

**Writing effective personas:** Describe observable behaviors. Good descriptions specify communication style (verbose vs. terse), frustration threshold (patient vs. abandons quickly), domain expertise level, and how the persona reacts when things go wrong.

### Scenarios

A Scenario describes the situation and the goal given to the simulated user.

```yaml
scenarios:
  - id: constrained-analysis
    name: Constrained analysis
    description: >
      Upload q3_sales.csv and ask the target to analyse Q3 revenue by region
      using the median, exclude outliers, and produce a report with charts.
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier, referenced by Tasks |
| `name` | Yes | Human-readable Scenario name |
| `description` | Yes | What the simulated user will attempt |

### Tasks (Test Cases)

Each Task selects one Scenario and one Persona. It also specifies the files,
Trial count, and measured Behaviours for that Test Case. Each selected Behaviour
supplies all its Criteria.

```yaml
tasks:
  - id: TC-001
    scenario_ref: constrained-analysis
    persona_ref: cooperative-delegator
    fixtures: [q3_sales.csv]
    num_trials: 1
    behaviour_refs: [EB-DA-1]
  - id: TC-002
    scenario_ref: constrained-analysis
    persona_ref: impatient-executive
    fixtures: [q3_sales.csv]
    num_trials: 1
    behaviour_refs: [EB-DA-1]
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | Yes | — | Unique Task identifier |
| `scenario_ref` | Yes | — | One Scenario ID |
| `persona_ref` | Yes | — | One Persona ID |
| `fixtures` | No | `[]` | Filenames in `fixtures/` to upload |
| `num_trials` | No | `3` | Number of independent runs; at least `1` |
| `behaviour_refs` | Yes for execution | `[]` | Measured Behaviour IDs. Each selected Behaviour must have Criteria |

**How runs are generated:** Each Task produces `num_trials` independent runs.
The example above produces two runs. Two Tasks can select the same Scenario and
Persona with different fixtures or Behaviours.

Keep Task IDs when you edit or reorder Tasks. Give new and copied Tasks
new IDs. Results and resume checks use the Task ID and Trial index.

Every reference must resolve to an existing ID. IDs must be unique across the
document. Each Scenario needs at least one Task. Each measured Behaviour needs
at least one Criterion and must be selected by a Task. A Task cannot repeat a Behaviour
or fixture reference.

Tasks also accept optional execution settings:

| Field | Default | Purpose |
|-------|---------|---------|
| `max_turns` | `20` | Maximum user-agent turns before the run stops |
| `timeout_minutes` | `15` | Time limit for the simulation run |
| `response_wait_ms` | `300000` | Response wait limit used by the runner, in milliseconds |
| `max_run_retries` | `null` | Use the runner's retry default; `0` disables run retries |

The three limits must be positive integers. `max_run_retries` accepts a
nonnegative integer or `null`. A value of `2` allows the initial attempt and
up to two retries. Task settings apply to every Trial of that Task and are
independent of Criterion Grader arguments.

For example, a Task can include:

```yaml
max_turns: 30
timeout_minutes: 20
response_wait_ms: 450000
max_run_retries: 0
```

### Grader References

Each Criterion names a grader class in `grader_fqn` and sets its arguments in `grader_args`,
a mapping whose keys are the fields of the grader's `args_model`. Tasks select Behaviour IDs
through `behaviour_refs`, and each selected Behaviour supplies all its Criteria.

```yaml
criteria:
  - id: AC-DA-1
    name: Finish within the trace budget
    description:
      given: a request for a Q3 revenue report
      when: the session ends
      then: the session used no more than 8 exchanges
    grader_fqn: metis.library.graders.TraceBudgetGrader
    grader_args:
      max_traces: 8
```

`grader_args` is validated before anything runs: an unknown key, a wrong type or a
`threshold` outside 0–1 stops the run and names the Criterion. Use `grader_args: {}` to take
every default. Every grader accepts `threshold` (default 0.5): a scored result passes when its
score is at least the threshold.

For a model-based grader, set the judge model once for the experiment and override it per
Criterion if needed:

```yaml
defaults:
  judge_model: gpt-4o-mini
```

Two Criteria can use the same grader with different arguments; each gets its own results,
identified by its Criterion ID. A trace budget does not change the engine's execution turn
limit.

### Working Reference

For a complete working example with personas, scenarios, fixtures, and graders already configured, see [`packages/engine/example-experiment/`](../../packages/engine/example-experiment/) and its [README](../../packages/engine/example-experiment/README.md).

---

## CLI Reference

The engine exposes three commands:

```bash
metis engine simulate --input-dir <source path> [simulation options]
metis engine simulate --resume --experiment-dir <output path> [simulation options]
metis engine evaluate --experiment-dir <output path> [evaluation options]
metis engine run --input-dir <source path> [simulation and evaluation options]
metis engine run --resume --experiment-dir <output path> [simulation and evaluation options]
```

`simulate` writes run records only. It prints the exact command needed to evaluate the output directory it created. `evaluate` scores the output directory that you name, uses its frozen input snapshot, and overwrites `logs/evaluate.log` and `outputs/reports/results.json`, then prints the `metis insights report` command that builds the report. `run` performs both phases.

### Simulation options

`simulate` and `run` work in one of two modes. Give the flags for exactly one mode:

- **New run:** `--input-dir <source>` — the directory with `specification.yaml` and `fixtures/`.
- **Resume:** `--resume --experiment-dir <output>` — an output directory that a previous `simulate` created. Both flags are needed together: `--experiment-dir` without `--resume` is an error, and `--resume` without `--experiment-dir` is an error.

The flags below are optional and apply to both modes:

| Flag | Default | Description |
|------|---------|-------------|
| `--concurrency N` / `-c N` | `5` | Max parallel simulation workers |
| `-v` / `-vv` | WARNING | Increase verbosity: `-v` for INFO, `-vv` for DEBUG |
| `--quiet` | `false` | Suppress all output below ERROR |
| `--no-tui` | `false` | Disable TUI dashboard (force linear log output) |
| `--log-format` | `text` | Log file format: `text` or `json` |
| `--log-dir` | co-located with results | Override the log output directory |

### Evaluation options

| Flag | Default | Description |
|------|---------|-------------|
| `--experiment-dir` | (required) | One output directory that `simulate` created, for example `experiments/execute/orca-eval-20260820-143000/`. It must hold an `inputs/` snapshot |
| `--langfuse-timeout` | `90` | Seconds to wait for Langfuse traces to appear |
| `-v` / `-vv` | WARNING | Increase evaluation logging verbosity |
| `--quiet` | `false` | Suppress all output below ERROR |

The `run` command accepts the union of the simulation and evaluation options. Its `--no-tui` option controls only the Simulation TUI. Evaluation always uses normal progress output.

### Concurrency

The `--concurrency N` flag runs N simulation workers in parallel. The default is `5`. Reduce to `1` for sequential execution or increase based on your target's capacity.

Runs are distributed round-robin across workers. Each worker processes its slice sequentially — one run at a time — while all workers run concurrently via `asyncio.gather`. How isolation and resource sharing work depends on the runner.

#### Playwright runner (browser-based)

Each worker gets its own browser context with an isolated login session and page. No shared state or cookie leakage between workers. All contexts share a single browser process.

#### API runner (OrcaApiRunner)

Each worker gets a **fresh `OrcaApiRunner` per run**, not one for the worker's lifetime. The factory (`OrcaApiRunnerFactory`) mints a new runner for each run, which goes through `setup` → `send_turn` (repeated) → `teardown`, then is discarded. Within a single run, turns are strictly sequential — there is no intra-run parallelism.

The factory owns three resources shared across all concurrent runners:

| Resource | Purpose |
|----------|---------|
| `httpx.AsyncClient` | Single connection pool for all HTTP calls |
| `SubmitRateLimiter` | Spaces submissions across all runners at the configured RPM (default: 6 RPM). Uses an `asyncio.Lock` so concurrent runners interleave in arrival order rather than racing. |
| `FixtureLibrary` | Caches uploaded fixture file IDs. Uses a per-fixture-name `asyncio.Lock` so only one runner uploads a given fixture; others wait and reuse the cached ID. |

The rate limiter is the key throttle: with `submit_rpm: 6`, all concurrent runners collectively share a budget of one submission every 10 seconds, regardless of the `--concurrency` value. Increasing concurrency overlaps polling and setup time across runs but does not increase submission throughput.

### Verbosity

| Level | Flag | What you see |
|-------|------|------|
| ERROR only | `--quiet` | Only fatal errors |
| WARNING | (default) | Warnings and errors |
| INFO | `-v` | Operational progress (scenario starts, phase transitions) |
| DEBUG | `-vv` | Full diagnostics (every LLM call, page action, trace fetch) |

The Simulation TUI and evaluation progress are visible regardless of verbosity level in an interactive terminal. Verbosity controls log detail. `--no-tui` changes simulation to linear output; it does not suppress evaluation progress.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HEADED=true` | Show the browser window (useful for debugging) |

### Interrupt Handling

- **First Ctrl+C:** finishes the current conversation turn gracefully, then stops
- **Second Ctrl+C:** force-aborts immediately

### Non-TTY Environments

The Simulation TUI auto-disables when stderr is not a terminal, such as in CI or when output is piped. Evaluation reports linear per-record progress in this case. Use `--no-tui` if you want linear simulation output in an interactive terminal.

---

## Writing Custom Graders

A grader subclasses `metis.library.grader.Grader`, names an args model, and implements one
async method. It sees only the session's Langfuse traces and the run's artifacts, never the
scenario or persona. The full rules are in the
[graders README](../../packages/library/src/metis/library/graders/README.md).

```python
from pydantic import Field

from metis.core.grading import GraderResult, GradingOutput
from metis.core.traces import GradingInput
from metis.library.grader import Grader, GraderArgs, LLMSettings


class AnswerLengthArgs(GraderArgs):
    max_chars: int = Field(default=2000, ge=1)


class AnswerLengthGrader(Grader[AnswerLengthArgs]):
    """Every answered trace stays under a character budget."""

    args_model = AnswerLengthArgs

    async def grade(self, input: GradingInput, llm: LLMSettings) -> GradingOutput:
        results = []
        for trace in input.traces:
            output = trace.root.output
            if not isinstance(output, str):
                results.append(
                    GraderResult(status="skipped", reason=f"{trace.id}: no text")
                )
                continue
            ok = len(output) <= self.args.max_chars
            results.append(
                GraderResult(
                    status="scored",
                    score=1.0 if ok else 0.0,
                    reason=f"{trace.id}: {len(output)} chars",
                )
            )
        return GradingOutput(results=results)
```

Put it in any importable module and name it on a Criterion:

```yaml
grader_fqn: my_package.graders.AnswerLengthGrader
grader_args:
  max_chars: 1200
```

A model-based grader's args extend `JudgeArgs` instead; it gets a resolved `self.args.model`
and makes calls through `llm.client`, a shared `AsyncOpenAI`.

---

## Troubleshooting

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "No traces found" or extraction times out | Langfuse timeout too short, bad credentials, or target not instrumented | Increase `--langfuse-timeout`, verify Langfuse keys in `.env`, confirm your target writes traces to Langfuse |
| "Fixture not found" error | Path is absolute or has a typo | Use the filename only (relative to `fixtures/`), verify the file exists in the fixtures directory |
| "could not be imported" | FQN typo or module not installed | Check the import path for typos, ensure the package containing the grader is installed in your venv |
| Simulation hangs indefinitely | Target unresponsive or page never finishes loading | Use `HEADED=true` to see the browser, increase the Task's `response_wait_ms` |
| Simulation TUI not appearing | Running in a non-TTY environment | Expected — the Simulation TUI requires an interactive terminal. Use linear output or run in a real terminal |
| Ctrl+C doesn't stop immediately | Graceful shutdown is finishing the current turn | Press Ctrl+C a second time to force-abort |
| "is not a subclass of metis.library.grader.Grader" | The FQN names something other than a grader | Subclass metis.library.grader.Grader[YourArgs] and set args_model = YourArgs |
| "has invalid grader_args" | A grader_args key is misspelt, has the wrong type, or is out of range | Fix the field the message names; keys must match the grader's args_model |
| Duplicate persona/scenario ID error | Two entries share the same `id` | Use unique IDs for every persona and scenario |

---

## Adapting to Your Target

The bundled example targets Orca through its API runner. You can supply a custom runner for a REST API, WebSocket endpoint, browser UI, or another interface.

This section covers:
1. Writing a custom `Runner` class
2. Wiring it into the engine via `runner_factory_ref`
3. Understanding the Profile hierarchy
4. The Langfuse requirement for evaluation
5. A minimal experiment template for new targets

### Writing a Custom Runner

The engine interacts with your target through two abstractions:

- **`Runner`** — handles a single simulation attempt (one persona × one scenario). It translates messages and actions into transport-specific calls and returns observations.
- **`RunnerFactory`** — manages shared resources (connection pools, browser instances) and creates fresh `Runner` instances per attempt.

#### The Runner ABC

Source: `packages/engine/src/metis/engine/simulation/runner.py`

```python
from abc import ABC, abstractmethod
from pathlib import Path

from metis.engine.simulation.types import ChosenAction, Observation, RunConfig


class Runner(ABC):
    """Transport layer — connects the simulation to a target."""

    @abstractmethod
    async def setup(self, config: RunConfig) -> None:
        """Prepare the connection (authenticate, open session).

        Called once per attempt before the turn loop starts.
        The config provides persona/scenario IDs and timeout settings.
        """

    @abstractmethod
    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        """Deliver user message + chosen actions, return the target's response.

        - message: the text the simulated user sends
        - actions: list of ChosenAction selected by the UserAgent from
          the previous Observation's available_actions
        - Returns: an Observation carrying the target's text reply, any
          artifacts produced, one ActionResult per action in `actions`,
          any turn-level notices, and the next set of available_actions.
          See docs/runner-contract.md for the binding rules.
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up (close HTTP session, release resources).

        Called once per attempt after the turn loop ends, even on failure.
        """

    @abstractmethod
    async def get_session_id(self) -> str | None:
        """Return the target's session identifier.

        The engine stores this in the run record for trace extraction.
        Return None if your target has no concept of sessions.
        """
```

#### Key Types

These Pydantic models are defined in `metis.engine.simulation.types`:

**`Observation`** — what the target returned after a turn:

```python
class Observation(BaseModel):
    text: str = ""  # Target's text reply
    artifacts: list[Artifact] = []  # Downloads/charts produced
    action_results: list[ActionResult] = []  # One per action you were handed
    response_notices: list[str] = []  # Turn-level problems, not per-action
    available_actions: list[ActionSlot] | None = None  # Three-state: list/[]/None
    status_labels: list[str] = []  # Status indicators shown in UI
```

`action_results` is per-action and positional: `action_results[i]` is your
verdict on `actions[i]`, and you owe exactly one row per action you were
handed — a dropped action is a contract violation the engine will raise on.
`response_notices` is for turn-level problems that belong to no single action.
`available_actions` is three-state and the distinction is load-bearing: a list
of slots means the runner looked and found these available; `[]` means the
runner looked and found nothing; `None` means nobody looked. The rules are
normative and live in [runner-contract.md](../runner-contract.md).

**`ActionSlot`** — one available action discovered per-turn:

```python
class ActionSlot(BaseModel):
    id: str  # Unique action identifier
    kind: str  # Action type (e.g. "file_upload", "button")
    label: str  # Human-readable label
    options: list[str] | None = None  # Choices for select/radio actions
```

**`ChosenAction`** — an action the UserAgent selected from `available_actions`:

```python
class ChosenAction(BaseModel):
    id: str  # Must match an ActionSlot.id from the observation
    value: str | None = None  # Action payload (filename, form value, etc.)
```

#### The RunnerFactory Protocol

```python
from pathlib import Path
from typing import Protocol

from metis.engine.simulation.runner import Runner


class RunnerFactory(Protocol):
    """Factory that manages shared resources and creates Runner instances."""

    async def start(self) -> None:
        """Acquire shared resources (open connection pool, launch browser)."""
        ...

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        """Create a fresh Runner for one attempt.

        - run_dir: where the run's record.json will be written
        - fixtures_dir: directory containing files selected by the Task
        """
        ...

    async def close(self) -> None:
        """Release shared resources."""
        ...
```

Additionally, the engine expects a `retry_defaults` property:

```python
@property
def retry_defaults(self) -> tuple[int, float]:
    """Return (run_max_retries, run_retry_delay_seconds)."""
    ...
```

The engine instantiates your factory with `factory_cls()` (no arguments). Read any configuration you need from environment variables in `__init__`.

#### Complete REST API Runner Example

Below is a complete, runnable implementation that drives a target exposing a JSON chat endpoint:

```python
"""REST API runner for a chat-based target."""

from __future__ import annotations

from pathlib import Path

import httpx

from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
    ActionResult,
    ActionSlot,
    ChosenAction,
    Observation,
    RunConfig,
)


class RestRunnerConfig:
    """Configuration loaded from environment variables."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key


class RestRunner(Runner):
    """Drives a target via its REST API."""

    def __init__(self, config: RestRunnerConfig, fixtures_dir: Path) -> None:
        self._config = config
        self._fixtures_dir = fixtures_dir
        self._client: httpx.AsyncClient | None = None
        self._session_id: str | None = None

    async def setup(self, config: RunConfig) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            timeout=config.response_wait_ms / 1000,
        )
        # Create a new session on the target
        resp = await self._client.post("/sessions", json={"persona": config.persona})
        resp.raise_for_status()
        self._session_id = resp.json()["session_id"]

    async def send_turn(self, message: str, actions: list[ChosenAction]) -> Observation:
        assert self._client is not None
        payload = {
            "session_id": self._session_id,
            "message": message,
            "actions": [a.model_dump() for a in actions],
        }
        resp = await self._client.post("/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Parse available_actions: if the API returns the field, use it (even if []);
        # if the API does not report available_actions, return None.
        available_actions = None
        if "available_actions" in data:
            available_actions = [ActionSlot(**a) for a in data["available_actions"]]

        return Observation(
            text=data.get("reply", ""),
            available_actions=available_actions,
            # One row per action, in the order you were handed them. Here the
            # example target accepts or rejects them wholesale, so every row
            # carries the same verdict; a real runner reports each separately.
            action_results=[
                ActionResult(action_index=i, succeeded=True)
                for i in range(len(actions))
            ],
            response_notices=data.get("notices", []),
        )

    async def teardown(self) -> None:
        if self._client:
            await self._client.aclose()

    async def get_session_id(self) -> str | None:
        return self._session_id


class RestRunnerFactory:
    """Factory for REST-based runners."""

    def __init__(self) -> None:
        import os

        base_url = os.environ["TARGET_API_URL"]
        api_key = os.environ["TARGET_API_KEY"]
        self._config = RestRunnerConfig(base_url=base_url, api_key=api_key)

    @property
    def retry_defaults(self) -> tuple[int, float]:
        return (2, 5.0)

    async def start(self) -> None:
        pass  # No shared resources needed for HTTP

    async def create(self, run_dir: Path, fixtures_dir: Path) -> Runner:
        return RestRunner(config=self._config, fixtures_dir=fixtures_dir)

    async def close(self) -> None:
        pass
```

#### Implementation Prerequisites

Before writing your runner:

1. **Understand the turn loop.** The engine calls `setup()` once, then alternates `send_turn()` until the UserAgent decides to stop, then calls `teardown()`. Your runner must be stateful enough to maintain a conversation session across turns.

2. **Return meaningful `available_actions`.** The UserAgent can only select from actions you surface in the `Observation`. If your target has buttons, file uploads, or forms, expose them as `ActionSlot` entries. If it's purely text-based, return an empty list — `[]` means "I looked and there is nothing on offer", which is different from `None`, meaning "I did not look". Return `None` only on a path where you genuinely never inspected the target's state.

3. **Handle `fixtures_dir`.** When a Task lists fixture files and the UserAgent chooses a `file_upload` action, the file path is relative to `fixtures_dir`. Your runner must handle uploading it (multipart POST, base64 encoding, etc.).

4. **Return a session ID.** The engine uses this for Langfuse trace extraction in the evaluation phase. If your target doesn't use Langfuse, return `None` — but evaluation will then be unavailable (see [Langfuse Requirement](#langfuse-requirement)).

### Wiring Your Runner into the Engine

Once you have a `RunnerFactory` class, tell the engine to use it via the `runner_factory_ref` field in `specification.yaml`.

#### The `runner_factory_ref` Field

Add `runner_factory_ref` at the top level of your experiment configuration. This
excerpt selects the REST runner and defines one Test Case:

```yaml
schema_version: 2
id: my-api-eval
runner_factory_ref: my_package.runners.RestRunnerFactory

personas:
  - id: cooperative
    name: Cooperative user
    description: A friendly, patient user.

scenarios:
  - id: basic-chat
    name: Basic chat
    description: Ask a simple question and verify the response.

tasks:
  - id: TC-001
    scenario_ref: basic-chat
    persona_ref: cooperative
    fixtures: []
    num_trials: 1
    behaviour_refs: [EB-CHAT-1]
```

Include the Target and Feature hierarchy as well. The
[minimal template](#minimal-template) shows the complete document and defines
Criterion `AC-CHAT-1`.

The value is a fully-qualified Python name pointing to your `RunnerFactory` class. The engine resolves it at load time using `importlib.import_module` — if the import fails or the class lacks `start`, `create`, or `close` methods, validation raises an error immediately.

`runner_factory_ref` is a required field — the engine does not default to any runner. You must always specify which `RunnerFactory` to use.

#### Resolution Logic

Source: `packages/engine/src/metis/engine/simulation/runner_resolver.py`

The engine performs these checks at experiment load time:

1. Split `runner_factory_ref` on the last `.` to get `(module_path, class_name)`
2. Import `module_path` — raises `ImportError` if not found
3. Get `class_name` from the module — raises `ImportError` if the attribute doesn't exist
4. Verify the class has callable `start`, `create`, and `close` methods — raises `TypeError` if any are missing

At simulation time (`packages/engine/src/metis/engine/cli.py:557-563`):

```python
factory_cls = resolve_runner_factory(experiment.runner_factory_ref)
runner_factory = factory_cls()
```

The engine calls your factory's constructor with no arguments. All configuration (credentials, URLs, feature flags) should come from environment variables read inside `__init__`.

#### Removing Playwright Dependencies

If your target is not browser-based:

1. **Playwright is optional.** A runner that does not use a browser does not need the Playwright extra.

2. **Set credentials for the selected runner.** The Orca API runner needs `ORCA_API_URL` and `ORCA_API_KEY`. The Orca browser runner needs `ORCA_URL`, `ORCA_USERNAME`, and `ORCA_PASSWORD`. A custom runner reads its own variables.

3. **Your `.env` only needs your own variables** plus the ones required by the engine core:
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` — needed if you want evaluation (trace extraction)
   - `OPENAI_API_KEY` — needed for the simulated user agent and LLM-judge graders
   - Any variables your own factory reads in `__init__()`

#### Installability Requirement

Your runner module must be importable from the environment where `metis engine simulate` runs. Options:

- **In-tree:** Place your runner under `packages/engine/src/metis/engine/simulation/runners/` and use the FQN `metis.engine.simulation.runners.myrunner.MyRunnerFactory`
- **External package:** Install your package into the same venv (`uv pip install ./my-runner-pkg`) and reference its FQN
- **Single file:** Place a `.py` file anywhere on `PYTHONPATH` and reference it

### Profile Configuration (specification.yaml)

The Profile contains Target context and the Feature, Behaviour, and Criterion
hierarchy, including Grader settings. The Experiment configuration contains Personas, Scenarios,
Tasks, the experiment ID, and the runner reference. The Specification combines
the Profile and Experiment configuration.
`specification.yaml` stores all these fields at the top level.

#### Relationship to the Specification

| Concern | Fields in `specification.yaml` | Purpose |
|---------|--------------------------------|---------|
| Simulation setup | `id`, `runner_factory_ref`, `personas`, `scenarios`, `tasks` | Select the runner and define each Test Case and its Trials |
| Evaluation requirements (Profile) | `target`, `features` | Describe the target, expected Behaviours, Criteria, and Grader settings |

Tasks select measured Behaviours from the Profile. Reports combine the planned Tasks and
recorded results to show whether the target meets those Criteria.

The engine freezes the document under the output directory's `inputs/` directory.
Reporting reads this copy and joins scores by Criterion ID. The report retains
the grader configuration used for each Criterion.

#### Schema Reference

The [JSON Schema](../../packages/core/schemas/specification.schema.json) provides
editor completion and shape validation. The engine also checks references and
coverage when it loads the document. From a specification in
`packages/engine/example-experiment/`, use this editor directive:

```yaml
# yaml-language-server: $schema=../../core/schemas/specification.schema.json
```

```yaml
schema_version: 2
id: <string>              # Experiment identifier
runner_factory_ref: <string>  # Importable RunnerFactory class
target:
  name: <string>           # Target name
  users: <string>          # Prose that describes the target users
  description: <string>    # Short description of what is evaluated
  detail: <string>         # Longer context about the evaluation scope

features:
  - id: <string>           # Unique feature identifier (e.g. "EP-3")
    name: <string>         # Human-readable feature name (e.g. "Data Analyst")
    description: <string>  # What the feature must achieve
    behaviours:
      - id: <string>       # Unique behaviour identifier (e.g. "EB-DA-1")
        name: <string>     # Human-readable behaviour name
        description: <string>       # Full behavioural description
        measured: <bool>            # Whether the evaluation measures this behaviour
        criteria:
          - id: <string>            # Acceptance criterion ID (e.g. "AC-DA-20a")
            name: <string>          # Human-readable criterion name
            description:
              given: <string>       # Precondition
              when: <string>        # Action or trigger
              then: <string>        # Expected outcome
            grader_fqn: <string>
            grader_args: {}         # Grader constructor arguments

personas:
  - id: <string>
    name: <string>
    description: <string>

scenarios:
  - id: <string>
    name: <string>
    description: <string>

tasks:
  - id: <string>
    scenario_ref: <scenario-id>
    persona_ref: <persona-id>
    behaviour_refs: [<behaviour-id>]
    fixtures: [<filename>]
    num_trials: <integer>
```

#### Field Descriptions

**`schema_version`** — the specification schema version. The current version is `2`. The engine requires this field and rejects an unsupported version.

**`target`** — top-level metadata:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Name of the target being evaluated |
| `users` | Yes | Prose that describes who uses the target |
| `description` | Yes | Short evaluation description |
| `detail` | No | Extended context about the evaluation's purpose and scope |

**`features[]`** — target functions or user workflows being evaluated:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Identifier (new wizard features use `F-N`) |
| `name` | Yes | Human-readable name |
| `description` | Yes | What the feature must achieve |
| `behaviours` | No | Expected behaviours; defaults to `[]` |

**`features[].behaviours[]`** — observable behaviors:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Identifier (conventionally `EB-<FEATURE>-N`) |
| `name` | Yes | Human-readable behaviour name |
| `description` | Yes | Full description of what the target must do |
| `measured` | No | `true` when the evaluation measures this behaviour; defaults to `false` |
| `criteria` | No | Acceptance criteria; defaults to `[]`. Measured Behaviours need Task coverage |

**`features[].behaviours[].criteria[]`** — acceptance criteria (Given/When/Then):

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Identifier (conventionally `AC-<FEATURE>-N`) |
| `name` | Yes | Human-readable criterion name |
| `description.given` | Yes | Precondition or setup state |
| `description.when` | Yes | User action or trigger |
| `description.then` | Yes | Expected system response or outcome |
| `grader_fqn` | Yes for execution | Fully-qualified grader class name; drafts can use `null` |
| `grader_args` | No | Constructor arguments; defaults to `{}` |

#### Minimal Example

This Profile excerpt defines a turn-budget requirement for a chatbot:

```yaml
target:
  name: My Chatbot
  users: People who need concise answers.
  description: Evaluate the number of turns used for direct questions.
  detail: Tests direct questions from cooperative users.

features:
  - id: EP-1
    name: General Chat
    description: Answer direct questions.
    behaviours:
      - id: EB-CHAT-1
        name: Keep conversations short
        description: Answer direct questions within a small turn budget.
        measured: true
        criteria:
          - id: AC-CHAT-1
            name: Short turn budget
            description:
              given: a user asks a factual question
              when: the session ends
              then: the session used no more than 4 exchanges
            grader_fqn: metis.library.graders.TraceBudgetGrader
            grader_args:
              max_traces: 4
```

Add the experiment ID, runner, Personas, Scenarios, and Tasks to make a complete
Specification. The [minimal template](#minimal-template) below shows these fields
together. Use `measured: true` for Behaviours selected by Tasks. Unmeasured
Behaviours and their Criteria can remain in the document. Every Criterion needs
a grader before the engine can load the specification.

### Langfuse Requirement

The `evaluate` command requires that your target writes traces to [Langfuse](https://langfuse.com). The engine uses the session ID returned by `Runner.get_session_id()` to fetch traces from Langfuse, then feeds them to your configured graders.

#### What This Means in Practice

| Phase | Langfuse needed? | What happens without it |
|-------|-----------------|------------------------|
| `simulate` | No | Simulation runs normally — the engine drives your target and writes trial records and logs |
| `evaluate` | **Yes** | Extraction fails — no traces to score. Graders receive empty inputs. |
| `run` (combined) | **Yes** (for eval) | Simulation succeeds, evaluation fails at the extraction step |

#### Simulation-Only Fallback

If your target does not instrument with Langfuse, you can still use METIS for simulation:

```bash
# Run simulation only — no trace extraction needed
metis engine simulate --input-dir my-experiment/
```

This produces trial records in `experiments/execute/<id>-<timestamp>/outputs/trials/`. You get:
- Outcome data (stop reason, turn count, duration)
- Collected artifacts
- The trial's `logs/`, which record each turn's message and response as plain text

You lose:
- A structured conversation transcript (METIS reads the conversation from Langfuse; trial records
  do not hold a copy)
- Grader scoring (requires traces)
- The structured HTML/JSON report
- Per-turn internal reasoning visible in traces

#### Adding Langfuse to Your Target

If you want evaluation, instrument your target with the Langfuse SDK:

1. Add `langfuse` to your target's dependencies
2. Wrap your LLM calls with Langfuse's `@observe` decorator or use the callback handler
3. Ensure each conversation session gets a consistent `session_id`
4. Return that `session_id` from your runner's `get_session_id()` method

The engine then fetches traces using:
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` from your `.env`
- The session ID from the run record
- A configurable timeout (`--langfuse-timeout`, default 90s) for traces to appear

### Writing Your Own Experiment

Use this template and checklist when creating an experiment from scratch for a new target.

#### Minimal Template

Save this as `my-experiment/specification.yaml`. Set `runner_factory_ref` to your installed factory.

```yaml
schema_version: 2
id: my-target-eval
runner_factory_ref: my_package.runners.MyRunnerFactory

target:
  name: My Chatbot
  users: People who need concise answers.
  description: Evaluate the number of turns used for direct questions.

features:
  - id: EP-1
    name: General Chat
    description: Answer direct questions.
    behaviours:
      - id: EB-CHAT-1
        name: Keep conversations short
        description: Answer direct questions within a small turn budget.
        measured: true
        criteria:
          - id: AC-CHAT-1
            name: Short turn budget
            description:
              given: a user asks a factual question
              when: the session ends
              then: the session used no more than 4 exchanges
            grader_fqn: metis.library.graders.TraceBudgetGrader
            grader_args:
              max_traces: 4

personas:
  - id: cooperative
    name: Cooperative user
    description: A patient user who gives requested details.

scenarios:
  - id: smoke-test
    name: Direct factual question
    description: Ask for the difference between a bar chart and a histogram.

tasks:
  - id: TC-001
    scenario_ref: smoke-test
    persona_ref: cooperative
    fixtures: []
    num_trials: 1
    behaviour_refs: [EB-CHAT-1]
```

#### Pre-Flight Checklist

Before running `metis engine simulate --input-dir my-experiment/`:

- [ ] **Runner accessible:** Your `RunnerFactory` class is importable from the current venv.
  ```bash
  python -c "from my_package.runners import MyRunnerFactory"
  ```

- [ ] **Environment variables set:** All variables your factory's `__init__()` reads are in `.env` or exported.
  ```bash
  # For custom runners: whatever your factory needs
  # For evaluation: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
  # For user agent / judge graders: OPENAI_API_KEY
  ```

- [ ] **Fixtures exist:** Every filename in a Task's `fixtures:` list exists in `my-experiment/fixtures/`.

- [ ] **References match:** Each Task selects an existing Scenario, Persona, and measured Behaviours. Every Scenario and measured Behaviour has Task coverage.

- [ ] **Graders importable:** Every Criterion's `grader_fqn` resolves to an installed class.
  ```bash
  python -c "from metis.library.graders import TraceBudgetGrader"
  ```

- [ ] **Dry-run validation:** Load the experiment to catch schema errors early:
  ```bash
  python -c "
  from pathlib import Path
  from metis.engine.simulation.types import Specification
  Specification.load_file(Path('my-experiment/specification.yaml'))
  "
  ```

#### Adding Complexity Incrementally

Start with the minimal template above, verify it runs end-to-end, then layer in complexity:

1. **Add fixtures** — put files in `fixtures/`, reference them in `tasks[].fixtures`, and ensure your runner handles `file_upload` actions
2. **Add personas** — write 2-3 personas with contrasting behavioral profiles, select each one in a Task through `persona_ref`
3. **Add graders** — start with code-graded graders (fast, deterministic), then add judge-graded graders
4. **Extend coverage** — define more Features, Behaviours, and Criteria, then select the Behaviours in Tasks
5. **Tune parameters** — adjust Criterion `grader_args` and Task `num_trials` based on observed runs
