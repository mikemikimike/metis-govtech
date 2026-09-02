# Evaluation Orchestrator

Runs configured metrics against Langfuse traces extracted from a completed simulation. Produces structured results consumed by the report generator.

## Architecture

```
evaluate(fetch_result, metric_refs)
  ├── _resolve_metrics()         — import metric classes by FQN, instantiate with args
  ├── _evaluate_turn_metrics()   — per-turn metrics against LLMTestCase objects
  └── _evaluate_session_metrics() — session metrics against ConversationalTestCase objects
```

The orchestrator splits metrics automatically by type:

| Metric base class | Test case type | Granularity |
|-------------------|---------------|-------------|
| `BaseMetric` | `LLMTestCase` (one per trace/turn) | Per-turn |
| `BaseConversationalMetric` | `ConversationalTestCase` (one per session) | Session-level |

Both types can be listed together in `experiment.yaml` — no annotation needed.

### Concurrency

Metrics within a turn (or session) run concurrently via `asyncio.gather`, gated by an `asyncio.Semaphore` (default: 50). Sync metrics (`async_mode=False`) are offloaded to a thread via `asyncio.to_thread` so they don't block the event loop.

Each metric is `deepcopy`'d before execution so concurrent runs don't share mutable state.

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes | — | API key shared by the LLM judge and user agent |
| `OPENAI_BASE_URL` | No | _(OpenAI default)_ | Endpoint override for judge calls (e.g. for a compatible proxy) |
| `JUDGE_MODEL` | No | `gpt-5.6-luna` | Model name for GEval-based judge metrics |
| `DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE` | No | `300` | Per-metric timeout in seconds |

The judge model is configured in `metis.library.metrics._judge` and shared by all GEval-based metrics.

## Input

The orchestrator takes a `FetchLangfuseResult` (from the extractor) and a list of `MetricRef` objects (from `experiment.yaml`). Metrics are resolved by FQN at runtime via `importlib.import_module`.

## Output

Returns an `EvalResult` containing:

- **`turn_results`** — per-turn metric scores, reasons, costs, and token counts
- **`session_results`** — session-level metric scores
- **`routing_summary`** — aggregate trace/session/routing statistics
- **`durations`** — wall-clock time for turn and session metric phases

Multiple `EvalResult` objects can be merged via `EvalResult.merge()` for aggregate reporting.

## Structure

```
evaluation/
├── orchestrator.py  — evaluate(), metric resolution, concurrent metric execution
└── types.py         — EvalResult, TurnResult, SessionResult, MetricResult, EvalDurations
```

The extractor (trace fetching from Langfuse) lives in `../extractor/`.
