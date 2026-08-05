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
# Run the example experiment
metis engine simulate --input-dir packages/engine/example-experiment/

# Headed mode (visible browser)
HEADED=true metis engine simulate --input-dir packages/engine/example-experiment/

# Verbose logging
metis engine simulate --input-dir packages/engine/example-experiment/ -vv

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
├── sessions/            # Per-run conversation records
└── reports/
    ├── report.json      # Machine-readable results
    └── report.html      # Visual report (open in browser)
```

## Available metrics

| Module | Covers |
|--------|--------|
| `metis.library.metrics.orchestration` | Routing, clarification, decomposition, delegation, synthesis |
| `metis.library.metrics.analysis` | Analytical correctness, scope, charts, reports |
| `metis.library.metrics.presentation` | Slide spec compliance, logical flow, source faithfulness |
| `metis.library.metrics.universal` | Constraint adherence, turn budget, clarification efficiency |
| `metis.library.metrics.session` | Session-level conversational metrics (full multi-turn) |

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
