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

The two Orca-specific runners under `runners/` are reference implementations for GovTech's Orca platform, not part of the framework contract:

| Runner | Transport | Notes |
|--------|-----------|-------|
| `orca_playwright` | Playwright (browser) | Drives Orca's web UI via a headless browser. Each worker gets its own browser context with isolated login. |
| `orca_api` | HTTP (`/api/v1`) | Drives Orca via its key-authenticated REST API. Turns are sequential within a run; concurrency comes from multiple runners sharing a rate limiter and fixture cache via the factory. See [`orca_api/README.md`](runners/orca_api/README.md) for the turn lifecycle, identifiers, and v1 endpoint coverage. |

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
├── runner.py          — Runner ABC and RunnerFactory protocol
├── runner_resolver.py — Resolves runner_factory_ref FQN to a class
├── experiment.py      — Experiment orchestrator (worker distribution, asyncio.gather)
├── orchestrator.py    — Single-run orchestration (turn loop, retries)
├── types.py           — Pydantic models (Specification, Scenario, Persona, Observation, ...)
├── config.py          — Shared configuration (retry defaults)
├── _contract.py       — Runner↔Observation contract enforcement (see docs/runner-contract.md)
├── exceptions.py      — Simulation-specific exceptions
├── _artifact_store.py — Artifact capture and storage
├── user_agent/        — LLM-powered user agent (persona embodiment)
└── runners/
    ├── _http.py           — Shared HTTP utilities (rate limiter, backoff, polling)
    ├── orca_playwright/   — Orca browser runner (auth, page actions, UI capture,
    │                        element resolution, recovery, retry)
    └── orca_api/          — Orca API runner (transport, fixtures, artifacts)
```
