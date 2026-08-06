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
# Run the example experiment (TUI auto-enabled in a terminal)
metis engine simulate --input-dir packages/engine/example-experiment/

# Headed mode (visible browser)
HEADED=true metis engine simulate --input-dir packages/engine/example-experiment/

# Verbosity — controls the TUI log tail and non-TUI stderr output.
# The TUI dashboard (progress bars, scenario status) is always visible regardless.
metis engine simulate --input-dir packages/engine/example-experiment/ -v    # INFO
metis engine simulate --input-dir packages/engine/example-experiment/ -vv   # DEBUG
metis engine simulate --input-dir packages/engine/example-experiment/ --quiet  # ERROR only

# Disable TUI (force linear output)
metis engine simulate --input-dir packages/engine/example-experiment/ --no-tui

# Structured log files (JSON lines)
metis engine simulate --input-dir packages/engine/example-experiment/ --log-format json

# Override log directory (default: co-located with results)
metis engine simulate --input-dir packages/engine/example-experiment/ --log-dir /tmp/my-logs

# Custom Langfuse timeout (default: 90s)
metis engine simulate --input-dir packages/engine/example-experiment/ --langfuse-timeout 120
```

## Experiments

An experiment is a directory containing an `experiment.yaml` and a `fixtures/` folder:

```
my-experiment/
├── experiment.yaml      # Personas, tasks, metrics, configuration
└── fixtures/            # Files uploaded during simulation
    └── data.csv
```

See [`example-experiment/`](example-experiment/) for a working reference.

Each run produces output in `experiments/<id>-<timestamp>/`:

```
experiments/orca-eval-20260730-143022/
├── inputs/              # Snapshot of experiment inputs
├── runs/                # Per-run conversation records
├── logs/
│   ├── simulate.log                                  # Orchestration timeline (index)
│   ├── simulate-direct-question_cooperative-01.log   # Per-run detail (always DEBUG)
│   ├── simulate-constrained-analysis_impatient-01.log
│   └── ...
└── reports/
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
