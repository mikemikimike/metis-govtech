# Simulation Framework

LLM-driven persona simulation for end-to-end testing of an AI assistant. Drives real conversations through a target via a pluggable runner and writes frozen run records for later evaluation.

## Architecture

```
CLI (sync) → run_experiment() → asyncio.run()
  └── RunnerFactory.start()
       ├── Worker 0: factory.create() → Runner → run slice
       ├── Worker 1: factory.create() → Runner → run slice
       └── ... (N workers, set by --concurrency)
```

```
User Agent (Python/AsyncOpenAI)  →  Runner  →  Target
```

- **User Agent** — embodies the persona, generates next messages; imported and called directly by the orchestrator
- **Runner** — translates messages and actions into transport-specific calls (HTTP API, browser automation, etc.) and returns observations
- **RunnerFactory** — manages shared resources (connection pools, browser instances, rate limiters) and creates fresh `Runner` instances per attempt

### Built-in runners

The two Orca-specific runners under `gen_1/runners/` are reference implementations for GovTech's Orca platform, not part of the framework contract:

| Runner | Transport | Notes |
|--------|-----------|-------|
| `orca_playwright` | Playwright (browser) | Drives Orca's web UI via a headless browser. Each worker gets its own browser context with isolated login. |
| `orca_api` | HTTP (`/api/v1`) | Drives Orca via its key-authenticated REST API. Turns are sequential within a run; concurrency comes from multiple runners sharing a rate limiter and fixture cache via the factory. See [`orca_api/README.md`](gen_1/runners/orca_api/README.md) for the turn lifecycle, identifiers, and v1 endpoint coverage. |

Both satisfy the normative [runner contract](../../../../../../docs/runner-contract.md); a custom runner must too.

Custom runners are selected via `runner_factory_ref` in `specification.yaml`. See the [Engine User Guide](../../../../../../docs/guide/engine.md#writing-a-custom-runner) for the `Runner` ABC, `RunnerFactory` protocol, and a complete REST example.

### Concurrency

Workers run concurrently via `asyncio.gather`. Each worker processes its slice of runs sequentially, creating a fresh `Runner` per run. How isolation and shared resources work is runner-specific — see the [Concurrency section](../../../../../../docs/guide/engine.md#concurrency) in the user guide.

### Artifacts

Charts (screenshotted as PNG) and downloads are captured and stored under the target session ID, which matches the Langfuse `session_id` for trace linking.

### Actions and uploads

Each turn the user agent emits a typed action list (`ChosenAction` — a union of `UploadFileAction`, `ButtonClickAction`, `FormFillAction`); the orchestrator passes it straight to `Runner.send_turn(message, actions)`, and the runner dispatches on the action type. Two properties are deliberate:

- **Uploads are gated by the scenario fixture allow-list, not by the target's per-turn permission.** A `file_upload` slot is offered for each `scenario.fixtures` entry not yet attached (and, in `orca_api`, not yet rejected) — synthetic, not derived from the target's current state. The **caller** validates an upload against that allow-list and the fixture's presence on disk before dispatch, withholding the action and reporting it as `withheld` if it fails; the runner never sees it. Neither side checks whether the target is prompting for a file this turn. This matches Orca, where attaching a file is a composer affordance available on any message.
- **Only the persona honors conversational "wait" cues.** If the target says "please wait until next turn," that stays natural-language text in the observation — nothing mechanically blocks an upload. The persona LLM is trusted to read the cue and hold the action. A premature upload is discovered only at the transport layer (a backend rejection in `orca_api`, marking the fixture spent; a browser interaction in `orca_playwright`), never pre-empted. A target that truly gated uploads per turn would need runner-level enforcement that does not exist today.

### LLM-call log

Every simulation LLM call goes through `llm_calls.parse_completion`, which writes one row per request to an `LLMCallLog`: a trial's calls to `outputs/trials/<id>/evidence/llm_calls.jsonl`, and calls made once per experiment (fixture descriptions) to `logs/llm_calls.jsonl`. Each row records the component, the requested and returned model, tokens in and out (`null` when the endpoint did not report them), latency, and any error. The wrapper retries failed requests itself, so a new caller must build its `AsyncOpenAI` client with `max_retries=0` to keep every attempt in the log.

### Transport log

`transport_log.LoggingTransport` wraps an `httpx` transport and writes every request and the response that answers it to `outputs/trials/<id>/evidence/log.jsonl`, so a retry loop above it gets one pair of entries per attempt with no help. Each entry has an ID, a kind (`request` or `response`), a role (`action` or `result`), the request it answers, a one-line summary written by code, redacted headers and a body. `Authorization` and each header named in the target binding's `secret_headers` are written as `***`; only header names are redacted, so a secret placed in a URL or body would be logged as sent. A body over 64 KB goes to `evidence/<id>.bin`, and a downloaded artifact is logged as an `ArtifactRef` (its path and SHA-256) instead of a copy. The log is for `gen_2`; `gen_1` does not write it.

`artifacts.ArtifactLedger` is the one place a `gen_2` runner records a file, as METIS's own `Artifact`. `record_download` saves the body under the last component of the target's name in `<trial>/artifacts/`, writing `<name>.part` and renaming it only once the bytes are whole and checked, so a partial download is never kept. A name that is taken becomes `name-1.ext`, `name-2.ext`; nothing already saved is overwritten and no entry is ever replaced. It returns the transport log's `ArtifactRef`. The byte check refuses a `.png`, `.jpg`, `.gif`, `.pdf`, `.docx`, `.xlsx`, `.pptx` or `.zip` that does not start with its type's signature, and any JSON document or JSON content type saved under a name that is not `.json`; a refused download leaves no file and no entry. A fixture has one entry however often it is uploaded: `record_upload` stamps the first upload's turn on it and adds nothing. The caller supplies `at_turn`. Each entry's `content_description` is one facts line written by code, never the file's content: name, type and size, and for a CSV its data rows, columns and header. Facts are computed once per distinct digest. `gen_1` does not use it.

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | API key for the user agent LLM |
| `OPENAI_BASE_URL` | No | Endpoint override; unset → default OpenAI endpoint |
| `USER_AGENT_MODEL` | No | User-agent model name (default: `gpt-5.6-luna`) |
| `USER_AGENT_MAX_TOKENS` | No | Max output tokens per turn (unset/empty → parameter omitted, provider default applies) |
| `USER_AGENT_TEMPERATURE` | No | Sampling temperature (unset/empty → parameter omitted, provider default applies) |

Runner-specific variables (e.g. `ORCA_URL`, `ORCA_API_URL`, `ORCA_API_KEY`) are documented in each runner's module docstring. Judge/evaluation variables (`JUDGE_API_KEY`, `JUDGE_BASE_URL`, `JUDGE_MODEL`) are documented in the [evaluation README](../evaluation/README.md).

## Running

Run from the project root. Use `uv run metis engine simulate` or activate the environment first.

```bash
metis engine simulate --input-dir path/to/my-experiment/
# Evaluate the output directory that simulate wrote. It prints this command.
metis engine evaluate --experiment-dir experiments/execute/my-experiment-20260820-143000/
```

Use `metis engine run --input-dir path/to/my-experiment/` for the combined simulation and evaluation flow.

Simulation uses the live TUI in a terminal. Evaluation uses a normal progress bar, reports linear per-record progress outside a terminal, and writes one complete `logs/evaluate.log` file.

## Structure

```
simulation/
├── factory.py         — RunnerFactory protocol
├── trial.py           — "Run one trial" seam; picks the generation from the factory
├── runner_resolver.py — Resolves runner_factory_ref FQN to a class
├── experiment.py      — Experiment orchestrator (worker distribution, asyncio.gather)
├── types.py           — Pydantic models (Specification, Scenario, Persona)
├── config.py          — Shared configuration (retry defaults)
├── exceptions.py      — Simulation-specific exceptions
├── _artifact_store.py — Artifact capture and storage
├── runner.py, runners/ — old import paths; re-export from gen_1
└── gen_1/             — today's simulator: typed actions on offered slots
    ├── trial.py           — Builds today's UserAgent and Orchestrator for one attempt
    ├── runner.py          — Runner ABC
    ├── types.py           — Actions, slots, Observation, user agent input/output
    ├── orchestrator.py    — Single-run orchestration (turn loop, retries)
    ├── _contract.py       — Runner↔Observation contract enforcement (see docs/runner-contract.md)
    ├── artifact_summarizer.py — LLM descriptions of fixtures and artifacts
    ├── user_agent/        — LLM-powered user agent (persona embodiment)
    └── runners/
        ├── _http.py           — Shared HTTP utilities (rate limiter, backoff, polling)
        ├── orca_playwright/   — Orca browser runner (auth, page actions, UI capture,
        │                        element resolution, recovery, retry)
        └── orca_api/          — Orca API runner (transport, fixtures, artifacts)
```
