# Evaluation Orchestrator

Runs configured graders against Langfuse traces extracted from a completed simulation. Produces structured results consumed by the report generator.

## Architecture

```
evaluate(fetch_result, grader_refs)
  ├── _resolve_graders()         — import grader classes by FQN, instantiate with args
  ├── _evaluate_turn_graders()   — per-turn graders against LLMTestCase objects
  └── _evaluate_session_graders() — session graders against ConversationalTestCase objects
```

The orchestrator splits graders automatically by type:

| Grader base class | Test case type | Granularity |
|-------------------|---------------|-------------|
| `BaseMetric` | `LLMTestCase` (one per trace/turn) | Per-turn |
| `BaseConversationalMetric` | `ConversationalTestCase` (one per session) | Session-level |

Both types can be listed together in `specification.yaml` — no annotation needed.

### Concurrency

Graders within a turn (or session) run concurrently via `asyncio.gather`, gated by an `asyncio.Semaphore` (default: 50). Sync graders (`async_mode=False`) are offloaded to a thread via `asyncio.to_thread` so they don't block the event loop.

Each grader is `deepcopy`'d before execution so concurrent runs don't share mutable state.

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes | — | API key shared by the LLM judge and user agent |
| `OPENAI_BASE_URL` | No | _(OpenAI default)_ | Endpoint override for judge calls (e.g. for a compatible proxy) |
| `JUDGE_MODEL` | No | `gpt-5.6-luna` | Model name for GEval-based judge graders |
| `DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE` | No | `300` | Per-grader timeout in seconds |

The judge model is configured in `metis.library.graders._judge` and shared by all GEval-based graders.

## Input

The orchestrator takes a `FetchLangfuseResult` (from the extractor) and a list of `GraderRef` objects resolved from Task Criterion references in `specification.yaml`. Graders are resolved by FQN at runtime via `importlib.import_module`.

## Output

Returns an `EvalResult` containing:

- **`turn_results`** — per-turn grader scores, reasons, costs, and token counts
- **`session_results`** — session-level grader scores
- **`routing_summary`** — aggregate trace/session/routing statistics
- **`durations`** — wall-clock time for turn and session grader phases

Multiple `EvalResult` objects can be merged via `EvalResult.merge()` for aggregate reporting.

## Structure

```
evaluation/
├── orchestrator.py  — evaluate(), grader resolution, concurrent grader execution
└── types.py         — EvalResult, TurnResult, SessionResult, GraderResult, EvalDurations
```

The extractor (trace fetching from Langfuse) lives in `../extractor/`.
