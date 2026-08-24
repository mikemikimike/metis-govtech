# Simulation Framework

LLM-driven persona simulation for end-to-end testing of an AI assistant. Drives real conversations through the target UI via Playwright and writes frozen run records for later evaluation.

> **Note:** The harness (auth flow, page selectors, session ID extraction) is currently
> tightly coupled to Orca. Adapting to a different target requires changes in
> `harness/_auth.py`, `harness/_ui_capture.py`, and `harness/_page_actions.py`.

## Architecture

```
CLI (sync) → run_experiment() → asyncio.run()
  └── async_playwright() → 1 browser
       ├── Worker 0: BrowserContext → Page → login → run slice
       ├── Worker 1: BrowserContext → Page → login → run slice
       └── ... (N workers, set by --concurrency)
```

```
User Agent (Python/AsyncOpenAI)  →  Environment (Python/async Playwright)  →  Target UI
```

- **User Agent** — embodies the persona, generates next messages; imported and called directly by the environment harness
- **Environment** — handles Playwright interactions, file uploads, form fills, and artifact capture
- **Artifacts** — charts (screenshotted as PNG) and downloads are captured and stored under the target session ID, which matches the Langfuse `session_id` for trace linking

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | Shared API key for the user agent and DeepEval judge metrics |
| `OPENAI_BASE_URL` | No | Shared endpoint override for both; unset → default OpenAI endpoint |
| `USER_AGENT_MODEL` | No | User-agent model name (default: `gpt-5.6-luna`) |
| `USER_AGENT_MAX_TOKENS` | No | Max output tokens per turn (default: `1024`) |
| `USER_AGENT_TEMPERATURE` | No | Sampling temperature (default: `0.7`) |
| `JUDGE_MODEL` | No | Judge model name (default: `gemini-3.5-flash-lite`) |

## Running

Run from the project root. Use `uv run metis engine simulate` or activate the environment first.

```bash
metis engine simulate --input-dir path/to/my-experiment/
# Evaluate the output directory that simulate wrote. It prints this command.
# The name holds the experiment id and the start time of the run.
metis engine evaluate --experiment-dir experiments/my-experiment-20260820-143000/
```

Use `metis engine run --input-dir path/to/my-experiment/` for the combined simulation and evaluation flow.

Simulation uses the live TUI in a terminal. Evaluation uses a normal progress bar, reports linear per-record progress outside a terminal, and writes one complete `logs/evaluate.log` file.

## Input directory structure

All inputs for an experiment live in a single flat directory:

```
my-experiment/
├── experiment.yaml   — personas, tasks, metric refs, fixtures
└── fixtures/
    └── *.csv / *.txt — fixture files referenced by tasks
```

See `example-experiment/` at the project root for a working example. The CLI validates that `experiment.yaml` exists in the input directory and that all fixture files referenced by tasks are present in `fixtures/`.

On each run, the full input directory is copied into `experiments/experiment-YYYY-MM-DD-{uuid}/inputs/` for reproducibility.

## Structure

```
simulation/
├── fixtures/          — Internal test data files (see fixtures/README.md)
├── user_agent/        — Python user agent (OpenAI-powered)
├── schema_test.py     — Schema sync tests
└── types.py           — Pydantic models (Experiment, ExperimentTask, Persona, SessionConfig, ...)
```
