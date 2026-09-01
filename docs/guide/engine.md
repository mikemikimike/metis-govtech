# Engine User Guide

## Introduction

metis-engine is the evaluation runtime for METIS. It drives a target system's web UI via Playwright using LLM-powered simulated user personas. It then extracts the resulting traces from Langfuse, runs configurable evaluation metrics, and generates reports. Simulation and evaluation are separate commands, with `run` available for the combined flow.

This guide is for anyone setting up evaluations against a web-based agentic system. By the end, you will have:

- A working local installation
- A completed evaluation run using the bundled example experiment
- The knowledge to write your own experiments with custom personas, scenarios, and metrics

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
make install
```

This installs all workspace dependencies and the Playwright browser binary.

### Environment Configuration

Copy the example environment file and fill in your credentials:

```bash
cp packages/engine/.env.example .env
```

The engine requires three groups of credentials:

| Group | Variables | Purpose |
|-------|-----------|---------|
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Trace storage and retrieval |
| OpenAI | `OPENAI_API_KEY` | Powers the LLM judge (metrics) and simulated user agent |
| Orca | `ORCA_URL`, `ORCA_USERNAME`, `ORCA_PASSWORD` | Target system URL and login credentials |

Optional tuning variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_AGENT_MODEL` | `gpt-5.6-luna` | Model used for the simulated user persona |
| `USER_AGENT_MAX_TOKENS` | _(unset)_ | Max tokens per user agent response; unset/empty → parameter omitted, provider default applies. Set explicitly (e.g. `4096`) for reasoning models where chain-of-thought tokens count against the limit |
| `USER_AGENT_TEMPERATURE` | _(unset)_ | Sampling temperature for the user agent; unset/empty → parameter omitted, provider default applies |
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

The directory `packages/engine/example-experiment/` contains a complete experiment definition written for Orca. The personas, task descriptions, fixture files, and metric selections assume Orca's specific multi-agent architecture.

```
example-experiment/
├── experiment.yaml      # Personas, scenarios, and metrics
├── profile.yaml         # Tasks, behaviours, criteria, and metrics
└── fixtures/            # Files uploaded during simulation
    ├── q3_sales.csv
    ├── q3_sales_corrupted.csv
    ├── q3_sales_v1.csv
    ├── q3_sales_v2.csv
    └── policy_document_adversarial.txt
```

### Run It

```bash
metis engine run --input-dir packages/engine/example-experiment/
```

To run the phases separately, use `simulate` first. It prints the exact `evaluate` command for the output directory it created. `evaluate` scores the directory that you name:

```bash
metis engine simulate --input-dir packages/engine/example-experiment/
metis engine evaluate --experiment-dir experiments/orca-eval-20260820-143000/
```

`experiments/orca-eval-20260820-143000/` is the output directory that `simulate` created. The name is only a sample: `simulate` makes the real name from the experiment `id` and the start time of the run, so use the path that `simulate` printed.

If simulation stops before all runs finish, continue the output directory that you name. `simulate` prints this exact command, so you never retype a timestamp:

```bash
metis engine simulate --resume --experiment-dir experiments/orca-eval-20260820-143000/
# or run the remaining simulation and then evaluate everything:
metis engine run --resume --experiment-dir experiments/orca-eval-20260820-143000/
```

Resume reads the experiment and the fixtures from the frozen `inputs/` snapshot in the named directory, not from the source directory. It retries only missing, invalid, or `system_error` records, and appends to the experiment-level simulation log. Extra run folders are ignored. A valid record is complete even if an artifact file is missing. Passing `--resume` with `--input-dir` is an error: the message lists the outputs that exist for the experiment `id` and names the correct flag.

### What You'll See

The engine launches a Simulation TUI for simulation:

- Progress bars for each scenario
- Per-run status (`pending → simulating → done/failed`)
- A scrolling log tail with recent events

Evaluation uses a normal, non-full-screen progress bar:

- One completed/total count for run records
- The current record and phase (`extracting` or `evaluating`)
- Failed records advance the bar after the warning is shown

The combined `run` command closes the Simulation TUI before it starts the evaluation progress bar. It performs four phases:

1. **Simulate** — the user agent interacts with Orca via Playwright
2. **Extract** — traces are fetched from Langfuse
3. **Evaluate** — metrics score the extracted traces
4. **Report** — results are written to disk

### Where Results Land

Each run produces output in `experiments/<id>-<timestamp>/`. The `reports/` directory is created by `evaluate` or `run`; simulation-only runs stop after `runs/` and `logs/`:

```
experiments/orca-eval-20260730-143022/
├── inputs/              # Snapshot of experiment inputs
├── runs/                # Per-run conversation records
├── logs/
│   ├── simulate.log                                  # Orchestration timeline
│   ├── evaluate.log                                  # Complete evaluation timeline
│   ├── simulate-direct-question_cooperative-01.log   # Per-run detail
│   └── ...
└── reports/             # created by evaluate or run
    ├── report.json      # Machine-readable results
    └── report.html      # Visual report (open in browser)
```

Use `logs/evaluate.log` to review extraction, each configured metric, the actual judge model reported by DeepEval, metric scores, pass or fail results, reasons, errors, cost, token counts, soft failures, hard failures, and final record counts for the latest evaluation attempt.

See the [report contract](report.md) for the report's scoring,
status, failure-evidence, and information-architecture rules.

### Debugging Tip

If a simulation behaves unexpectedly, run with a visible browser:

```bash
HEADED=true metis engine simulate --input-dir packages/engine/example-experiment/
```

---

## Experiment Configuration

An experiment is defined by a single `experiment.yaml` file placed alongside a `fixtures/` directory:

```
my-experiment/
├── experiment.yaml
├── profile.yaml
└── fixtures/
    └── my-data.csv
```

### Top-Level Fields

```yaml
schema_version: 1

id: my-evaluation
description: >
  End-to-end evaluation of the target system's routing and analysis capabilities.
```

| Field | Required | Description |
|-------|----------|-------------|
| `schema_version` | Yes | Always `1` (current version) |
| `id` | Yes | Identifier used in the output directory name |
| `description` | Yes | Free-text purpose of the experiment |

### Personas

Personas are LLM-powered simulated users. During simulation, each persona interacts with the target system according to its behavioral profile — communication style, patience level, domain expertise, and goals.

```yaml
personas:
  - id: cooperative-delegator
    description: >
      A mid-level programme manager who is comfortable with AI tools, has time
      to engage, and communicates in a friendly, conversational way. They
      disclose information eagerly and cooperate fully, with a moderate
      frustration threshold.

  - id: impatient-executive
    description: >
      A time-poor senior director who delegates everything and expects systems
      to just work. They communicate in curt bullet points with no pleasantries
      and have a very low frustration threshold.
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier, referenced by scenarios |
| `description` | Yes | Behavioral profile the LLM user agent embodies |

**Writing effective personas:** Focus on observable behaviors rather than internal states. Good descriptions specify communication style (verbose vs. terse), frustration threshold (patient vs. abandons quickly), domain expertise level, and how the persona reacts when things go wrong.

### Scenarios

A scenario defines a specific evaluation task: what the simulated user will attempt, which personas will attempt it, what files they'll upload, and which metrics assess the result.

```yaml
scenarios:
  - id: constrained-analysis
    description: >
      Upload q3_sales.csv and ask the system to analyse Q3 revenue by region
      using the median (not the mean), exclude outliers, and produce a report
      with charts.
    num_trials: 1
    max_turns: 20
    timeout_minutes: 15
    fixtures:
      - q3_sales.csv
    persona_refs:
      - cooperative-delegator
      - impatient-executive
    metric_refs:
      - metis.library.metrics.RoutingAccuracyMetric
      - metis.library.metrics.ConstraintAdherenceMetric
      - metis.library.metrics.TurnBudgetMetric:
          max_turns: 8
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | Yes | — | Unique identifier |
| `description` | Yes | — | What the simulated user will attempt (given to the user agent as its goal) |
| `num_trials` | No | `1` | How many times each persona repeats this scenario |
| `fixtures` | No | `[]` | Files in `fixtures/` to upload during simulation |
| `persona_refs` | Yes | — | List of persona `id`s to run this scenario with |
| `metric_refs` | No | `[]` | Metrics to evaluate the resulting traces (see below) |
| `max_turns` | No | `20` | Maximum user-agent turns before the run is terminated |
| `timeout_minutes` | No | `15` | Wall-clock timeout for the entire simulation run |
| `response_wait_ms` | No | `300000` | Milliseconds to wait for the target system to respond before timing out |
| `max_run_retries` | No | — | Cap on run retry attempts; omit to use the engine default |

**How runs are generated:** Each scenario produces `len(persona_refs) × num_trials` independent runs. For the example above, that's 2 personas × 1 trial = 2 runs.

### Metric References

Metrics are referenced by their fully-qualified Python class name. Three syntaxes are supported:

**Plain (no parameters):**

```yaml
metric_refs:
  - metis.library.metrics.RoutingAccuracyMetric
```

**With parameters (single-key mapping):**

```yaml
metric_refs:
  - metis.library.metrics.TurnBudgetMetric:
      max_turns: 8
```

**Explicit form (for programmatic construction or clarity):**

```yaml
metric_refs:
  - fqn: metis.library.metrics.TurnBudgetMetric
    args:
      max_turns: 8
```

Parameters are passed directly to the metric class's `__init__`. See [Writing Custom Metrics](#writing-custom-metrics) for how to define metrics that accept parameters.

### Working Reference

For a complete working example with personas, scenarios, fixtures, and metrics already configured, see [`packages/engine/example-experiment/`](../../packages/engine/example-experiment/) and its [README](../../packages/engine/example-experiment/README.md).

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

`simulate` writes run records only. It prints the exact command needed to evaluate the output directory it created. `evaluate` scores the output directory that you name, uses its frozen input snapshot, and overwrites `logs/evaluate.log`, `reports/report.json`, and `reports/report.html`. `run` performs both phases.

### Simulation options

`simulate` and `run` work in one of two modes. Give the flags for exactly one mode:

- **New run:** `--input-dir <source>` — the directory with `experiment.yaml`, `profile.yaml` and `fixtures/`.
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
| `--experiment-dir` | (required) | One output directory that `simulate` created, for example `experiments/orca-eval-20260820-143000/`. It must hold an `inputs/` snapshot |
| `--langfuse-timeout` | `90` | Seconds to wait for Langfuse traces to appear |
| `-v` / `-vv` | WARNING | Increase evaluation logging verbosity |
| `--quiet` | `false` | Suppress all output below ERROR |

The `run` command accepts the union of the simulation and evaluation options. Its `--no-tui` option controls only the Simulation TUI. Evaluation always uses normal progress output.

### Concurrency

The `--concurrency N` flag runs N simulation workers in parallel. Each worker gets its own isolated login session and page — no shared state between workers.

The default is `5`. Reduce to `1` for sequential execution or increase based on your target system's capacity.

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
| `DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE` | Override DeepEval's per-metric timeout (default: 300s) |

### Interrupt Handling

- **First Ctrl+C:** finishes the current conversation turn gracefully, then stops
- **Second Ctrl+C:** force-aborts immediately

### Non-TTY Environments

The Simulation TUI auto-disables when stderr is not a terminal, such as in CI or when output is piped. Evaluation reports linear per-record progress in this case. Use `--no-tui` if you want linear simulation output in an interactive terminal.

---

## Writing Custom Metrics

The built-in metrics in `metis.library.metrics` cover common evaluation dimensions, but you can write your own for domain-specific needs.

### Metric Basics

A metric is a Python class that:
1. Extends `SyncBaseMetric` (from `metis.library.metrics`)
2. Defines a `tags` ClassVar
3. Implements `measure(self, test_case: LLMTestCase) -> float`
4. Implements `is_successful(self) -> bool`
5. Exposes a `__name__` property

### Code-Graded Metric Example

A metric that programmatically checks a property of the trace without calling an LLM judge:

```python
"""Check that the session completed within the allowed turn budget."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase

from metis.library.metrics._base import SyncBaseMetric
from metis.library.metrics._types import LlmTestCaseMetadata


class TurnBudgetMetric(SyncBaseMetric):
    """Session completed within the allowed turn budget."""

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "code-graded")

    def __init__(self, threshold: float = 1.0, max_turns: int = 10):
        self.threshold = threshold
        self.max_turns = max_turns
        self.score = 0.0
        self.reason = ""
        self.success = False

    def measure(self, test_case: LLMTestCase) -> float:
        metadata = cast(LlmTestCaseMetadata, test_case.metadata or {})
        total_turns = metadata.get("total_turns")

        if total_turns is None:
            self.skipped = True
            self.score = 1.0
            self.reason = "total_turns not present in metadata — skipped"
            self.success = True
            return self.score

        self.score = 1.0 if total_turns <= self.max_turns else 0.0
        self.reason = f"Session used {total_turns} turn(s) (budget: {self.max_turns})"
        self.success = self.score >= self.threshold
        return self.score

    @property
    def __name__(self):
        return "Turn Budget"

    def is_successful(self) -> bool:
        return self.success
```

### Judge-Graded Metric Example

A metric that uses GEval-style prompting to assess a qualitative dimension:

```python
"""Evaluate the quality of direct chatbot responses."""

from typing import ClassVar, cast

from deepeval.test_case import LLMTestCase, SingleTurnParams

from metis.library.metrics._base import (
    EVIDENCE_INSTRUCTION,
    SyncBaseMetric,
    _ContextAwareGEval,
)
from metis.library.metrics._judge import _get_judge_model
from metis.library.metrics._types import LlmTestCaseMetadata


class ResponseQualityMetric(SyncBaseMetric):
    """Evaluates whether the response is helpful, appropriate, and concise."""

    tags: ClassVar[tuple[str, ...]] = ("universal", "per-turn", "judge-graded")

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold
        self.score = 0.0
        self.reason = ""
        self.success = False
        self._geval = None

    def _get_geval(self):
        if self._geval is None:
            self._geval = _ContextAwareGEval(
                name="Response Quality",
                model=_get_judge_model(),
                criteria=(
                    "Evaluate the system's response.\n\n"
                    "The 'input' is the user's request.\n"
                    "The 'actual_output' is the system's response.\n\n"
                    "Rate on three dimensions:\n"
                    "1. Helpful: Does it answer the question?\n"
                    "2. Tone: Is the tone appropriate?\n"
                    "3. Concise: Is it appropriately brief?\n\n"
                    "Score 1.0 if excellent on all. "
                    "Score 0.5 if mixed. "
                    "Score 0.0 if poor." + EVIDENCE_INSTRUCTION
                ),
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                ],
                threshold=0.6,
            )
        return self._geval

    def measure(self, test_case: LLMTestCase) -> float:
        geval = self._get_geval()
        geval.measure(test_case)
        self.score = geval.score
        self.reason = geval.reason
        self.success = (self.score or 0) >= self.threshold
        self._absorb_geval_cost(geval)
        return self.score or 0.0

    @property
    def __name__(self):
        return "Response Quality"

    def is_successful(self) -> bool:
        return self.success
```

### Making Your Metric Discoverable

Place your metric in any importable Python module and reference it by its fully-qualified name in `metric_refs`:

```yaml
metric_refs:
  - my_package.metrics.ResponseQualityMetric
```

The module must be importable from the environment where `metis engine evaluate` runs. If it's part of the METIS workspace, place it under `packages/library/src/metis/library/metrics/` and re-export from `__init__.py`.

### Accepting Parameters from YAML

Any `__init__` parameter beyond `threshold` can be passed from `experiment.yaml` using the map syntax:

```yaml
metric_refs:
  - my_package.metrics.TurnBudgetMetric:
      max_turns: 4
```

The YAML values are passed as keyword arguments to `__init__`.

### The Tags Convention

Every metric must define a `tags` ClassVar as a tuple of strings:

```python
tags: ClassVar[tuple[str, ...]] = ("orchestration", "per-turn", "code-graded")
```

| Dimension | Values | Meaning |
|-----------|--------|---------|
| Component | `orchestration`, `analysis`, `presentation`, `universal` | Which system component the metric evaluates |
| Granularity | `per-turn`, `session-level` | Whether it scores individual turns or the full session |
| Grading | `code-graded`, `judge-graded` | Whether it uses programmatic logic or an LLM judge |

### Available Metadata

The `test_case.metadata` dict (typed as `LlmTestCaseMetadata`) provides:

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | `str` | Langfuse trace ID |
| `session_id` | `str` | Langfuse session ID |
| `turn_index` | `int` | Current turn number (0-indexed) |
| `total_turns` | `int` | Total turns in the session |
| `observations` | `list` | Raw Langfuse observations |
| `tool_calls` | `list` | Tool calls extracted from the trace |
| `delegation` | `dict \| None` | Delegation event (target agent, if any) |
| `assistant_messages` | `list` | All assistant messages in the session |
| `clarification_requests` | `list` | Requests for user input |
| `artifacts` | `dict` | Downloaded/detected artifacts |
| `scenario` | `object` | The `Scenario` object from experiment config |
| `persona` | `object` | The `Persona` object from experiment config |

---

## Troubleshooting

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "No traces found" or extraction times out | Langfuse timeout too short, bad credentials, or target system not instrumented | Increase `--langfuse-timeout`, verify Langfuse keys in `.env`, confirm your target writes traces to Langfuse |
| "Fixture not found" error | Path is absolute or has a typo | Use the filename only (relative to `fixtures/`), verify the file exists in the fixtures directory |
| "Metric import failed" | FQN typo or module not installed | Check the import path for typos, ensure the package containing the metric is installed in your venv |
| Simulation hangs indefinitely | Target system unresponsive or page never finishes loading | Use `HEADED=true` to see the browser, increase `response_wait_ms` in the scenario config |
| Simulation TUI not appearing | Running in a non-TTY environment | Expected — the Simulation TUI requires an interactive terminal. Use linear output or run in a real terminal |
| Ctrl+C doesn't stop immediately | Graceful shutdown is finishing the current turn | Press Ctrl+C a second time to force-abort |
| "Metric is not a subclass of BaseMetric" | Class doesn't inherit from the correct base | Ensure your metric extends `SyncBaseMetric` or `deepeval.metrics.BaseMetric` |
| Duplicate persona/scenario ID error | Two entries share the same `id` | Use unique IDs for every persona and scenario |

---

## Adapting to Your Target System

The engine's default target is Orca — a browser-based multi-agent system driven via Playwright. If your target system exposes a REST API, WebSocket endpoint, or any non-browser interface, you can replace the Playwright runner with a custom implementation.

This section covers:
1. Writing a custom `Runner` class
2. Wiring it into the engine via `runner_factory_ref`
3. Understanding `profile.yaml`
4. The Langfuse requirement for evaluation
5. A minimal experiment template for new targets

### Writing a Custom Runner

The engine interacts with your target system through two abstractions:

- **`Runner`** — handles a single simulation attempt (one persona × one scenario). It translates messages and actions into transport-specific calls and returns observations.
- **`RunnerFactory`** — manages shared resources (connection pools, browser instances) and creates fresh `Runner` instances per attempt.

#### The Runner ABC

Source: `packages/engine/src/metis/engine/simulation/runner.py`

```python
from abc import ABC, abstractmethod
from pathlib import Path

from metis.engine.simulation.types import ChosenAction, Observation, RunConfig


class Runner(ABC):
    """Transport layer — connects the simulation to a target system."""

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
        - Returns: an Observation with the target's text reply, any
          artifacts produced, errors, and the next set of available_actions
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Clean up (close HTTP session, release resources).

        Called once per attempt after the turn loop ends, even on failure.
        """

    @abstractmethod
    async def get_session_id(self) -> str | None:
        """Return the target system's session identifier.

        The engine stores this in the run record for trace extraction.
        Return None if your system has no concept of sessions.
        """

    async def recover(self) -> None:
        """Attempt lightweight recovery after a transient error.

        Default: no-op. Override to implement retry logic (e.g., refresh
        a page, reconnect a WebSocket). Called before re-attempting a turn.
        """
```

#### Key Types

These Pydantic models are defined in `metis.engine.simulation.types`:

**`Observation`** — what the target system returned after a turn:

```python
class Observation(BaseModel):
    text: str = ""  # Target's text reply
    artifacts: list[Artifact] = []  # Downloads/charts produced
    errors: list[str] = []  # Error messages from the target
    available_actions: list[ActionSlot] = []  # What the user can do next
    status_labels: list[str] = []  # Status indicators shown in UI
```

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
        - fixtures_dir: directory containing files listed in the scenario's fixtures
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

Below is a complete, runnable implementation that drives a target system exposing a JSON chat endpoint:

```python
"""REST API runner for a chat-based target system."""

from __future__ import annotations

from pathlib import Path

import httpx

from metis.engine.simulation.runner import Runner
from metis.engine.simulation.types import (
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
    """Drives a target system via its REST API."""

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
        return Observation(
            text=data.get("reply", ""),
            available_actions=[
                ActionSlot(**a) for a in data.get("available_actions", [])
            ],
            errors=data.get("errors", []),
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

2. **Return meaningful `available_actions`.** The UserAgent can only select from actions you surface in the `Observation`. If your target has buttons, file uploads, or forms, expose them as `ActionSlot` entries. If it's purely text-based, return an empty list.

3. **Handle `fixtures_dir`.** When a scenario lists fixture files and the UserAgent chooses a `file_upload` action, the file path is relative to `fixtures_dir`. Your runner must handle uploading it (multipart POST, base64 encoding, etc.).

4. **Return a session ID.** The engine uses this for Langfuse trace extraction in the evaluation phase. If your target doesn't use Langfuse, return `None` — but evaluation will then be unavailable (see [Langfuse Requirement](#langfuse-requirement)).

### Wiring Your Runner into the Engine

Once you have a `RunnerFactory` class, tell the engine to use it via the `runner_factory_ref` field in `experiment.yaml`.

#### The `runner_factory_ref` Field

Add `runner_factory_ref` at the top level of your experiment configuration:

```yaml
schema_version: 1

id: my-api-eval
description: Evaluate target system via REST API

runner_factory_ref: my_package.runners.RestRunnerFactory

personas:
  - id: cooperative
    description: A friendly, patient user.

scenarios:
  - id: basic-chat
    description: Ask a simple question and verify the response.
    persona_refs:
      - cooperative
    metric_refs:
      - metis.library.metrics.ResponseQualityMetric
```

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

1. **You don't need to uninstall Playwright.** The import only happens when the Playwright factory is instantiated (the default path). With `runner_factory_ref` set, the engine never touches Playwright code.

2. **Don't set `ORCA_*` environment variables.** The OrcaPlaywright factory's `OrcaPlaywrightRunnerConfig.load()` raises a `ValueError` listing missing variables (`ORCA_URL`, `ORCA_USERNAME`, `ORCA_PASSWORD`) — but this code path is never reached when `runner_factory_ref` points elsewhere.

3. **Your `.env` only needs your own variables** plus the ones required by the engine core:
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` — needed if you want evaluation (trace extraction)
   - `OPENAI_API_KEY` — needed for the simulated user agent and LLM-judge metrics
   - Any variables your own factory reads in `__init__()`

#### Installability Requirement

Your runner module must be importable from the environment where `metis engine simulate` runs. Options:

- **In-tree:** Place your runner under `packages/engine/src/metis/engine/simulation/runners/` and use the FQN `metis.engine.simulation.runners.myrunner.MyRunnerFactory`
- **External package:** Install your package into the same venv (`uv pip install ./my-runner-pkg`) and reference its FQN
- **Single file:** Place a `.py` file anywhere on `PYTHONPATH` and reference it

### Profile Configuration (profile.yaml)

The `profile.yaml` file describes **what** your target system does — its product identity, the tasks it handles, and the acceptance criteria that define correct behavior. The engine uses it during report generation to map simulation outcomes to structured pass/fail results.

`profile.yaml` lives alongside `experiment.yaml` in your experiment directory:

```
my-experiment/
├── experiment.yaml      # HOW to run: personas, scenarios, metrics
├── profile.yaml         # WHAT to evaluate: tasks, behaviours, criteria
└── fixtures/
```

#### Relationship to experiment.yaml

| Concern | File | Purpose |
|---------|------|---------|
| Simulation setup | `experiment.yaml` | Personas, scenarios, fixtures, metrics, runner |
| Evaluation semantics | `profile.yaml` | Product identity, task definitions, acceptance criteria |

The experiment defines *how* to run evaluations. The profile defines *what* correct behavior looks like. Reports combine both: experiment results are graded against profile criteria.

#### Schema Reference

```yaml
product:
  name: <string>           # Target system name
  users: <string>          # Comma-separated persona IDs that test this product
  summary: <string>        # One-line description of what's being evaluated
  detail: <string>         # Longer context about the evaluation scope

tasks:
  - id: <string>           # Unique task identifier (e.g. "EP-3")
    name: <string>         # Human-readable task name (e.g. "Data Analyst")
    behaviours:
      - id: <string>       # Unique behaviour identifier (e.g. "EB-DA-1")
        interaction_type: <string>  # How the user interacts (e.g. "chat")
        statement: <string>         # Full behavioural description
        priority: <bool>            # Whether this is a priority behaviour
        criteria:
          - id: <string>            # Acceptance criterion ID (e.g. "AC-DA-20a")
            interaction_type: <string>
            given: <string>         # Precondition
            when: <string>          # Action/trigger
            then: <string>          # Expected outcome
            priority: <bool>
```

#### Field Descriptions

**`product`** — top-level metadata:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Name of the target system being evaluated |
| `users` | Yes | Comma-separated list of persona IDs (must match `experiment.yaml` persona IDs) |
| `summary` | Yes | One-line evaluation description |
| `detail` | No | Extended context about the evaluation's purpose and scope |

**`tasks[]`** — capabilities being evaluated:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable identifier (conventionally `EP-N`) |
| `name` | Yes | Human-readable name |
| `behaviours` | Yes | List of expected behaviours for this task |

**`tasks[].behaviours[]`** — observable behaviors:

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable identifier (conventionally `EB-<TASK>-N`) |
| `interaction_type` | Yes | Interaction mode (`chat`, `upload`, etc.) |
| `statement` | Yes | Full description of expected behaviour — what the system should do |
| `priority` | No | `true` if this is a priority behaviour for reporting |
| `criteria` | Yes | Acceptance criteria that define pass/fail |

**`tasks[].behaviours[].criteria[]`** — acceptance criteria (Given/When/Then):

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Stable identifier (conventionally `AC-<TASK>-N`) |
| `interaction_type` | Yes | Interaction mode |
| `given` | Yes | Precondition or setup state |
| `when` | Yes | User action or trigger |
| `then` | Yes | Expected system response or outcome |
| `priority` | No | `true` if this criterion is high-priority |

#### Minimal Example

```yaml
product:
  name: My Chatbot
  users: cooperative, impatient
  summary: Evaluate chatbot response quality and safety.
  detail: Tests core chat capabilities across persona types.

tasks:
  - id: EP-1
    name: General Chat
    behaviours:
      - id: EB-CHAT-1
        interaction_type: chat
        statement: >
          The chatbot responds helpfully and concisely to direct questions,
          providing accurate information without unnecessary elaboration.
        priority: true
        criteria:
          - id: AC-CHAT-1a
            interaction_type: chat
            given: a user asks a factual question
            when: the chatbot receives the message
            then: >
              it responds with a correct, concise answer within 2 turns
            priority: true
          - id: AC-CHAT-1b
            interaction_type: chat
            given: a user asks an ambiguous question
            when: the chatbot cannot determine intent
            then: >
              it asks one clarifying question before attempting an answer
            priority: false
```

#### When profile.yaml is Optional

`profile.yaml` is required for report generation. If the file is absent:

- `simulate` runs normally — no impact on simulation
- `evaluate` runs metrics and writes `report.json` with metric scores, but skips the structured criteria pass/fail mapping
- The HTML report omits the task/behaviour/criteria breakdown

For early experimentation or simulation-only workflows, you can omit `profile.yaml` entirely.

### Langfuse Requirement

The `evaluate` command requires that your target system writes traces to [Langfuse](https://langfuse.com). The engine uses the session ID returned by `Runner.get_session_id()` to fetch traces from Langfuse, then feeds them to your configured metrics.

#### What This Means in Practice

| Phase | Langfuse needed? | What happens without it |
|-------|-----------------|------------------------|
| `simulate` | No | Simulation runs normally — the engine drives your target and records conversations |
| `evaluate` | **Yes** | Extraction fails — no traces to score. Metrics receive empty inputs. |
| `run` (combined) | **Yes** (for eval) | Simulation succeeds, evaluation fails at the extraction step |

#### Simulation-Only Fallback

If your target system does not instrument with Langfuse, you can still use METIS for simulation:

```bash
# Run simulation only — no trace extraction needed
metis engine simulate --input-dir my-experiment/
```

This produces run records with full conversation transcripts in `experiments/<id>-<timestamp>/runs/`. You get:
- Complete user-agent ↔ target conversation logs
- Outcome data (stop reason, turn count, duration)
- Collected artifacts

You lose:
- Metric scoring (requires traces)
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

Use this template and checklist when creating an experiment from scratch for a new target system.

#### Minimal Template

```yaml
schema_version: 1

id: my-target-eval
description: >
  Evaluation of [target system] [capabilities being tested].

runner_factory_ref: my_package.runners.MyRunnerFactory

personas:
  - id: cooperative
    description: >
      A patient, friendly user who communicates clearly, provides all
      requested information, and has a high frustration threshold.

scenarios:
  - id: smoke-test
    description: >
      Send a simple greeting and verify the system responds coherently.
    num_trials: 1
    max_turns: 5
    timeout_minutes: 5
    persona_refs:
      - cooperative
    metric_refs:
      - metis.library.metrics.ResponseQualityMetric
```

#### Pre-Flight Checklist

Before running `metis engine simulate --input-dir my-experiment/`:

- [ ] **Runner accessible:** Your `RunnerFactory` class is importable from the current venv.
  ```bash
  python -c "from my_package.runners import MyRunnerFactory; print('OK')"
  ```

- [ ] **Environment variables set:** All variables your factory's `__init__()` reads are in `.env` or exported.
  ```bash
  # For custom runners: whatever your factory needs
  # For evaluation: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
  # For user agent / judge metrics: OPENAI_API_KEY
  ```

- [ ] **Fixtures exist:** Every filename in a scenario's `fixtures:` list exists in `my-experiment/fixtures/`.

- [ ] **Persona IDs match:** Every `persona_refs` entry in every scenario matches a `personas[].id`.

- [ ] **Metrics importable:** Every `metric_refs` FQN resolves to an installed class.
  ```bash
  python -c "from metis.library.metrics import ResponseQualityMetric; print('OK')"
  ```

- [ ] **Dry-run validation:** Load the experiment to catch schema errors early:
  ```bash
  python -c "
  from pathlib import Path
  from metis.engine.simulation.types import Experiment
  Experiment.load_file(Path('my-experiment/experiment.yaml'))
  print('Valid')
  "
  ```

#### Adding Complexity Incrementally

Start with the minimal template above, verify it runs end-to-end, then layer in complexity:

1. **Add fixtures** — put files in `fixtures/`, reference them in `scenarios[].fixtures`, and ensure your runner handles `file_upload` actions
2. **Add personas** — write 2-3 personas with contrasting behavioral profiles, add them to `persona_refs`
3. **Add metrics** — start with code-graded metrics (fast, deterministic), then add judge-graded metrics
4. **Add profile.yaml** — define tasks, behaviours, and criteria to get structured reports
5. **Tune parameters** — adjust `max_turns`, `timeout_minutes`, `response_wait_ms`, `num_trials` based on observed runs
