# metis-engine

Evaluation engine for METIS — simulation harness, trace extraction, metric execution, and report generation.

## What it does

1. **Simulate** — drives the target system's UI via Playwright with LLM-powered user personas
2. **Extract** — fetches resulting Langfuse traces and builds DeepEval test cases
3. **Evaluate** — runs 50+ metrics (code-graded and LLM-judge) against the traces
4. **Report** — generates terminal summary, JSON, and self-contained HTML reports

## Setup

```bash
# From the monorepo root
make install                    # installs all deps + Playwright browser

# Configure environment
cp packages/engine/.env.example .env
# Fill in: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, OPENAI_API_KEY,
#          ORCA_URL, ORCA_USERNAME, ORCA_PASSWORD
```

## Running

```bash
# Run end-to-end (Simulation TUI, then evaluation progress bar)
metis engine run --input-dir packages/engine/example-experiment/

# Or run the phases separately, in this order. simulate prints the evaluate command.
# The --experiment-dir value is the output directory that simulate created.
metis engine simulate --input-dir packages/engine/example-experiment/
metis engine evaluate --experiment-dir experiments/orca-eval-20260820-143000/

# Headed mode (visible browser)
HEADED=true metis engine simulate --input-dir packages/engine/example-experiment/

# Verbosity controls log detail, not progress displays.
metis engine simulate --input-dir packages/engine/example-experiment/ -v    # INFO
metis engine simulate --input-dir packages/engine/example-experiment/ -vv   # DEBUG
metis engine simulate --input-dir packages/engine/example-experiment/ --quiet  # ERROR only

# Disable the Simulation TUI (force linear simulation output)
metis engine simulate --input-dir packages/engine/example-experiment/ --no-tui

# Structured log files (JSON lines)
metis engine simulate --input-dir packages/engine/example-experiment/ --log-format json

# Override log directory (default: co-located with results)
metis engine simulate --input-dir packages/engine/example-experiment/ --log-dir /tmp/my-logs

# Concurrent simulation (2 parallel browser contexts)
metis engine simulate --input-dir packages/engine/example-experiment/ --concurrency 2

# Custom Langfuse timeout for evaluation (default: 90s)
metis engine evaluate --experiment-dir experiments/orca-eval-20260820-143000/ --langfuse-timeout 120
```

| Command | Reads | Writes |
|---------|-------|--------|
| `simulate` | `experiment.yaml` and `fixtures/` from `--input-dir` | `experiments/<id>-<timestamp>/runs/` |
| `evaluate` | `runs/` from the `--experiment-dir` output directory, plus the Langfuse traces it points to | `reports/` in that same output directory |

> **Important:** `evaluate` must only be run after `simulate`. It scores an existing simulation output rather than producing one, so if the directory holds no `inputs/` snapshot it exits 1 and tells you to run `simulate` first.

The two commands take different paths. `simulate` takes the source experiment as `--input-dir`. `evaluate` takes one simulation output directory as `--experiment-dir`, so the scored output never depends on timestamps. `simulate` prints the exact `evaluate` command for the directory it created.

`experiments/orca-eval-20260820-143000/` in the examples above is only a sample name. `simulate` makes the real name from the experiment `id` and the start time of the run. Use the path that `simulate` printed.

Evaluation has no TUI option. It uses a normal progress bar in a terminal and linear per-record progress in a non-interactive environment.

### Concurrency

The `--concurrency N` flag runs N browser contexts in parallel on a single browser process. Each worker gets its own isolated login session and page — no shared state, no cookie leakage between workers.

Runs are distributed round-robin across workers for balanced load. Start with `--concurrency 2` and increase based on target system capacity. The default (`1`) preserves sequential behaviour.

## Experiments

An experiment is a directory containing an `experiment.yaml` and a `fixtures/` folder:

```
my-experiment/
├── experiment.yaml      # Personas, tasks, metrics, configuration
└── fixtures/            # Files uploaded during simulation
    └── data.csv
```

See [`example-experiment/`](example-experiment/) for a working reference.

Each run produces output in `experiments/<id>-<timestamp>/`. Reports appear after `evaluate` or `run`:

```
experiments/orca-eval-20260730-143022/
├── inputs/              # Snapshot of experiment inputs
├── runs/                # Per-run conversation records
├── logs/
│   ├── simulate.log                                  # Orchestration timeline (index)
│   ├── evaluate.log                                  # Models, metrics, outputs, timeline
│   ├── simulate-direct-question_cooperative-01.log   # Per-run detail (always DEBUG)
│   ├── simulate-constrained-analysis_impatient-01.log
│   └── ...
└── reports/             # created by evaluate or run
    ├── report.json      # Machine-readable results
    └── report.html      # Visual report (open in browser)
```

## Available metrics

All metrics are imported from `metis.library.metrics` (e.g. `metis.library.metrics.RoutingAccuracyMetric`).

Each metric class carries a `tags` ClassVar for classification:

| Tag dimension | Values |
|---------------|--------|
| Component | `orchestration`, `analysis`, `presentation`, `universal` |
| Granularity | `per-turn`, `session-level` |
| Grading | `code-graded`, `judge-graded` |

## Programmatic usage

```python
from metis.engine import evaluate, generate_report, fetch_by_session_id
from metis.engine.extractor import get_langfuse_client
```

## Schema management

Pydantic models in `src/metis/engine/simulation/types.py` are the source of truth. After modifying models:

```bash
make -C packages/engine generate-schema
```

See [`schemas/README.md`](schemas/README.md) for versioning rules.
