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
| `USER_AGENT_MODEL` | `gpt-4o-mini` | Model used for the simulated user persona |
| `USER_AGENT_MAX_TOKENS` | `1024` | Max tokens per user agent response |
| `USER_AGENT_TEMPERATURE` | `0.7` | Sampling temperature for the user agent |
| `HEADED` | `false` | Set to `true` to show the browser window |

### Verify Installation

```bash
metis engine simulate --help
```

You should see the simulate command's help text with all available flags.

---

## Quick Start

Run the bundled example experiment to verify everything works end-to-end.

### The Example Experiment

The directory `packages/engine/example-experiment/` contains a complete experiment definition written for Orca. The personas, task descriptions, fixture files, and metric selections assume Orca's specific multi-agent architecture.

```
example-experiment/
├── experiment.yaml      # Personas, scenarios, and metrics
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
metis engine evaluate --experiment-dir <output path> [evaluation options]
metis engine run --input-dir <source path> [simulation and evaluation options]
```

`simulate` writes run records only. It prints the exact command needed to evaluate the output directory it created. `evaluate` scores the output directory that you name, uses its frozen input snapshot, and overwrites `logs/evaluate.log`, `reports/report.json`, and `reports/report.html`. `run` performs both phases.

### Simulation options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-dir` | (required) | Directory containing `experiment.yaml` and `fixtures/` |
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
from metis.library.metrics._types import TraceMetadata


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
        metadata = cast(TraceMetadata, test_case.metadata or {})
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
from metis.library.metrics._types import TraceMetadata


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

The `test_case.metadata` dict (typed as `TraceMetadata`) provides:

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
