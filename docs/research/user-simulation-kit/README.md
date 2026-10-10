# User Simulation Kit

This directory helps you get started quickly on a prototype simulator. It holds what a
prototype ingests (personas, scenarios, tasks and fixtures, in a simple format) and what
it must produce, so you do not have to dig them out of the METIS repository.

**Start with the problem statement**,
[`../user-simulation-problem-statement.md`](../user-simulation-problem-statement.md). It
explains what is wrong with today's simulator, the evidence, the terms used here, the
constraints and the ideas to weigh. This README is the practical companion to it.

**The simulator should work with any target.** The design must be target-agnostic, but
the first implementation only needs to be an HTTP runner against Orca's REST API. Orca is
the first target to validate against, because it is the only one with a ready-made set
of inputs, and because today's simulator already runs against it, which gives a baseline
to compare with. Treat Orca as a test case, not as the shape of the design.

## What is in this kit

```
user-simulation-kit/
├── README.md                     this file
├── .env                          credentials, ready to use (private, git-ignored)
├── .env.example                  the same variables, without values
├── inputs/                       Orca's evaluation inputs
│   ├── personas.yaml             7 personas (3 are defined but unused by any task)
│   ├── scenarios.yaml            8 scenarios
│   ├── tasks.yaml                18 tasks: scenario × persona × fixtures × budget
│   └── fixtures/                 the files the user agent may upload
└── reference/
    ├── output-contract.md        what a simulator must record for each trial
    └── user-agent-prompts.md     the exact prompts today's user agent is given
```

Everything in `inputs/` comes from METIS's Orca evaluation specification. Nothing was
invented for this kit. The *format* (persona, scenario, task, fixtures) is the same for
every target; only the *content* here was written for Orca.

```
 inputs/ ──▶ your prototype ──conversation──▶ target (first: Orca)
                  │                                 │
                  ▼                                 ▼ traces
        one record per trial               Langfuse ──▶ METIS evaluation
        (reference/output-contract.md)           (not part of this work)
```

## How the inputs fit together

A **task** pairs one scenario with one persona, lists the fixtures the user agent may
upload, and sets a budget. Each task runs `num_trials` times (3 in every task here), and
each **trial** is one conversation, which becomes one session on the target. The full
Orca set is 18 tasks × 3 = 54 trials.

| Budget field | Meaning |
| --- | --- |
| `max_turns` | stop after this many user turns (20) |
| `timeout_minutes` | stop after this much wall-clock time (15) |
| `response_wait_ms` | how long to wait for the target to answer one turn (5 minutes) |

Start small. `TC-001` (a direct question, no files) is the simplest task. The
`direct-question` scenario needs no uploads, so it exercises the conversation loop
without the file handling.

## Validating against Orca

`.env` already holds everything needed to run against Orca:

| Variable | What it is for |
| --- | --- |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | the LLM that acts as the user agent, and any runner agent. The endpoint is OpenAI-compatible |
| `ORCA_API_URL`, `ORCA_API_KEY` | Orca's REST API. Send the key as `Authorization: Bearer <key>` |

Keep `.env` private. Do not commit it, paste it into prompts or logs, or share it
further. If the Orca key stops working, ask the Orca team for a new one.

These facts are specific to Orca; a different target will have its own equivalents.

- **Orca's API specification is the single source of truth.** Orca publishes it under
  the API base URL as an OpenAPI 3.1 document (`/api/v1/openapi.json`) and as browsable
  docs (`/api/v1/docs`). Both need no API key. The Orca team owns the API and the
  specification, so ask them about anything it does not cover. This kit does not repeat
  it.
- **The current host uses a self-signed TLS certificate.** Clients need certificate
  checking turned off, or the certificate trusted explicitly, before the first request
  succeeds.
- **Orca's session ID is also its Langfuse session ID.** That is how evaluation finds
  the traces, so a simulator must capture it for every trial. Every target needs some
  equivalent link to its traces.
- **Check Orca's usage allowance before a run** with `GET /api/v1/usage`. Once a shared
  allowance is spent, Orca silently switches to a cheaper model, and its data-analysis
  features can stop working while Orca carries on replying. One past experiment lost
  most of its trials this way without anyone noticing.
- **The inputs and today's prompts assume Orca's design.** The scenarios and personas
  expect an orchestrator that hands work to a data-analyst agent and a slide-maker
  agent. Today's user-agent prompt also tells the user agent to pick the fast model in
  Orca's "AI Model" dropdown. A new simulator should not carry knowledge like this in
  its own code or prompts.
